"""Next.js admin paneli uchun API.

Faqat Next.js serveri chaqiradi (X-Site-Key). Brauzer Django'ni ko'rmaydi.
Kirish faqat Telegram bot orqali: bot bergan bir martalik havola → 8 soatlik sessiya tokeni.
Login/parol yo'q. Sessiya faqat PanelAccess'i bor (botda ruxsat berilgan) foydalanuvchiga amal qiladi;
ruxsat o'chirilsa — token darhol yaroqsiz.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from functools import wraps

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Q, Value
from django.db.models.functions import Replace
from django.db.models.fields.files import FieldFile
from django.forms.models import model_to_dict
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .bot_api import use_link
from .models import (Activity, Appeal, ArchItem, CatalogPage, ImageSize, Flat, FlatLayout, FlatLayoutImage, InfraPoint, Milestone, InteriorSlide, LobbyFeature, Project, ProjectImage,
                     PanelAccess, SalesOffice)
from .telegram import category

SESSION_AGE = 8 * 60 * 60


# ---------- yordamchilar ----------

def _err(msg, status=400, **extra):
    return JsonResponse({"error": msg, **extra}, status=status)


def _site_key_ok(request) -> bool:
    return hmac.compare_digest(request.headers.get("X-Site-Key", ""), settings.SITE_API_KEY)


def _fingerprint(user) -> str:
    # Parol hash'i o'zgarsa — barcha eski tokenlar yaroqsiz
    return hashlib.sha256(user.password.encode()).hexdigest()[:16]


def _body(request) -> dict:
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
    return request.POST.dict()


def _client_ip(request) -> str:
    """Next serveri yuborgan haqiqiy mijoz IP'si."""
    return request.headers.get("X-Client-IP", "")[:64] or request.META.get("REMOTE_ADDR", "")


def panel_view(methods=("GET",), auth=True):
    def deco(fn):
        @csrf_exempt
        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            if not _site_key_ok(request):
                return _err("forbidden", 403)
            if request.method not in methods:
                return _err("method", 405)
            if auth:
                header = request.headers.get("Authorization", "")
                try:
                    data = signing.loads(header.removeprefix("Bearer ").strip(), salt="panel-session", max_age=SESSION_AGE)
                except signing.BadSignature:
                    return _err("unauthorized", 401)
                user = get_user_model().objects.filter(pk=data.get("uid"), is_active=True, is_staff=True).first()
                if (user is None or data.get("fp") != _fingerprint(user)
                        or not PanelAccess.objects.filter(user=user).exists()):  # botdagi ruxsat o'chirilgan
                    return _err("unauthorized", 401)
                request.panel_user = user
            return fn(request, *args, **kwargs)
        return wrapper
    return deco


# ---------- kirish (faqat Telegram bot havolasi) ----------

@panel_view(methods=("POST",), auth=False)
def telegram_login(request):
    access = use_link(str(_body(request).get("token", "")), ip=_client_ip(request))
    if access is None:
        return _err("Havola eskirgan yoki ishlatilgan. Botdan yangi havola oling.", 401)
    return JsonResponse(_session(access.user))


def _session(user) -> dict:
    token = signing.dumps({"uid": user.pk, "fp": _fingerprint(user)}, salt="panel-session")
    return {"token": token, "maxAge": SESSION_AGE, "name": user.get_full_name() or user.get_username()}


@panel_view()
def me(request):
    u = request.panel_user
    return JsonResponse({"username": u.get_username(), "name": u.get_full_name() or u.get_username()})


# ---------- bosh sahifa ----------

@panel_view()
def dashboard(request):
    flats = Flat.objects.aggregate(
        sotuvda=Count("id", filter=Q(status=Flat.Status.AVAILABLE)),
        band=Count("id", filter=Q(status=Flat.Status.BOOKED)),
        sotilgan=Count("id", filter=Q(status=Flat.Status.SOLD)),
    )
    recent = Appeal.objects.select_related("project")[:8]
    return JsonResponse({
        "projects": Project.objects.count(),
        "flats": flats,
        "appealsNew": Appeal.objects.filter(state=Appeal.State.NEW).count(),
        "recent": [_appeal(a) for a in recent],
    })


def _appeal(a: Appeal) -> dict:
    return {"id": a.id, "kind": a.get_kind_display(), "category": category(a), "name": a.name, "phone": a.phone,
            "email": a.email, "company": a.company, "inn": a.inn, "docNumber": a.doc_number,
            "subject": a.subject, "message": a.message, "country": a.country, "note": a.note,
            "project": a.project.title if a.project else None, "flat": a.flat_id,
            "state": a.state, "stateLabel": a.get_state_display(), "created": a.created_at.isoformat()}


@panel_view(methods=("GET", "POST"))
def appeals(request, pk=None):
    if request.method == "POST" and pk:
        state = _body(request).get("state")
        if state not in Appeal.State.values:
            return _err("holat noto'g'ri")
        Appeal.objects.filter(pk=pk).update(state=state)
        return JsonResponse({"ok": True})
    g = request.GET
    qs = Appeal.objects.select_related("project")
    # Davr: bugun / kecha / 7 kun / 30 kun (Toshkent vaqti bo'yicha)
    today = timezone.localdate()
    periods = {"bugun": (today, today), "kecha": (today - timedelta(days=1), today - timedelta(days=1)),
               "hafta": (today - timedelta(days=6), today), "oy": (today - timedelta(days=29), today)}
    if g.get("davr") in periods:
        start, end = periods[g["davr"]]
        qs = qs.filter(created_at__date__gte=start, created_at__date__lte=end)
    if g.get("manba") in Appeal.Source.values:
        qs = qs.filter(source=g["manba"])
    q = g.get("q", "").strip()[:60]
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        # Telefon bazada «+998 90 123 45 67» ko'rinishida — bo'sh joy/chiziqsiz solishtiramiz
        bare = Replace(Replace(Replace("phone", Value(" "), Value("")), Value("-"), Value("")), Value("+"), Value(""))
        qs = qs.annotate(phone_bare=bare).filter(
            Q(name__icontains=q) | Q(company__icontains=q) | (Q(phone_bare__contains=digits) if len(digits) >= 3 else Q(pk__in=[])))
    counts = dict(qs.values_list("state").annotate(n=Count("id")))  # holat bo'yicha — filtrlar ichida
    if g.get("state") in Appeal.State.values:
        qs = qs.filter(state=g["state"])
    return JsonResponse({"items": [_appeal(a) for a in qs[:200]],
                         "total": qs.count(),
                         "states": [{"value": v, "label": l, "count": counts.get(v, 0)} for v, l in Appeal.State.choices],
                         "sources": [{"value": v, "label": l} for v, l in Appeal.Source.choices if v != Appeal.Source.FOREIGN]})


# ---------- umumiy CRUD ----------

def _form(model, fields):
    return forms.modelform_factory(model, fields=fields)


KINDS = {
    "project": {
        "model": Project, "label": "Loyiha",
        "groups": [
            ("Asosiy", ["title", "slug", "status", "klass", "tagline", "color", "is_published", "order"]),
            ("Rasmlar", ["hero", "cover", "logo", "genplan"]),
            ("Loyiha haqida", ["description", "about_image", "about_video", "stat_blocks", "stat_queues",
                               "floors", "flats", "area", "handover", "features"]),
            ("Lobbi", ["lobby_title", "lobby_text", "lobby_image"]),
            ("Joylashuv", ["address", "latitude", "longitude", "office"]),
            ("Onlayn", ["live_url", "tour_url"]),
        ],
    },
    "arch": {"model": ArchItem, "label": "Arxitektura kartasi", "parent": "project",
             "groups": [("", ["title", "text", "image", "order"])]},
    "interior": {"model": InteriorSlide, "label": "Ichki makon slaydi", "parent": "project",
                 "groups": [("", ["title", "text", "image", "order"])]},
    "lobby": {"model": LobbyFeature, "label": "Lobbi afzalligi", "parent": "project",
              "groups": [("", ["icon", "label", "order"])]},
    "infra": {"model": InfraPoint, "label": "Infratuzilma nuqtasi", "parent": "project",
              "groups": [("", ["category", "name", "latitude", "longitude"])]},
    "gallery": {"model": ProjectImage, "label": "Galereya rasmi", "parent": "project",
                "groups": [("", ["image", "caption", "order"])]},
    "catalog": {"model": CatalogPage, "label": "Katalog sahifasi", "parent": "project",
                "groups": [("", ["image", "order"])]},
    "history": {"model": Milestone, "label": "Tarixiy sana",
                "groups": [("", ["year", "title", "text", "image"])]},
    "activity": {"model": Activity, "label": "Faoliyat (mukofot, yutuq)",
                 "groups": [("", ["year", "organization", "title", "image"])]},
    "flat": {"model": Flat, "label": "Xonadon",
             "groups": [("", ["building", "number", "floor", "kind", "rooms", "area", "status", "price", "show_price", "plan"])]},
    "layout": {"model": FlatLayout, "label": "Xonadon turi", "parent": "project",
               "groups": [("", ["rooms", "area", "description", "parts"])]},
    "layoutimage": {"model": FlatLayoutImage, "label": "Xonadon rasmi", "parent": "layout",
                    "groups": [("", ["image", "caption", "order"])]},
    "office": {"model": SalesOffice, "label": "Savdo ofisi",
               "groups": [("", ["name", "address", "phone", "hours", "latitude", "longitude", "photo", "order"])]},
}


def _fields(kind) -> list[str]:
    return [f for _, group in KINDS[kind]["groups"] for f in group]


def _field_schema(model, name) -> dict:
    f = model._meta.get_field(name)
    t = {
        "ImageField": "image", "FileField": "file", "TextField": "textarea", "BooleanField": "bool",
        "PositiveSmallIntegerField": "number", "PositiveIntegerField": "number", "DecimalField": "decimal",
        "ForeignKey": "select", "URLField": "url", "SlugField": "slug",
    }.get(f.get_internal_type(), "text")
    if f.choices:
        t = "select"
    if isinstance(f, models.ImageField):  # get_internal_type() ImageField uchun ham "FileField" qaytaradi
        t = "image"
    if name == "color":
        t = "color"
    out = {"name": name, "label": str(f.verbose_name).capitalize(), "type": t, "help": str(f.help_text or ""),
           "required": not f.blank and not f.has_default() and not f.null}
    size = next((v for v in f.validators if isinstance(v, ImageSize)), None)
    if size:
        out["size"] = {"minW": size.min_w, "minH": size.min_h, "ratio": list(size.ratio) if size.ratio else None}
    if t == "file":
        out["accept"] = "video/mp4,video/webm"
    elif t == "image":
        out["accept"] = "image/jpeg,image/png,image/webp"
    if f.choices:
        out["choices"] = [{"value": v, "label": str(l)} for v, l in f.choices]
    elif t == "select":  # ForeignKey
        out["choices"] = [{"value": o.pk, "label": str(o)} for o in f.related_model.objects.all()]
    return out


def _serialize(kind, obj) -> dict:
    data = {"id": obj.pk}
    for name in _fields(kind):
        value = getattr(obj, name if KINDS[kind]["model"]._meta.get_field(name).get_internal_type() != "ForeignKey" else name + "_id")
        if isinstance(value, FieldFile):
            value = value.url if value else None
        elif value is not None and not isinstance(value, (str, int, bool, float, list, dict)):  # JSON — o'zicha
            value = str(value)
        data[name] = value
    if kind == "project":
        data["counts"] = {k: getattr(obj, rel).count() for k, rel in
                          (("arch", "arch_items"), ("interior", "interior_slides"), ("lobby", "lobby_features"),
                           ("infra", "infra_points"), ("gallery", "images"), ("catalog", "catalog_pages"))}
        data["flatTotal"] = Flat.objects.filter(building__project=obj).count()  # o'chirish oynasida ogohlantirish uchun
    return data


@panel_view()
def schema(request):
    return JsonResponse({
        kind: {"label": cfg["label"], "parent": cfg.get("parent"),
               "groups": [{"title": title, "fields": [_field_schema(cfg["model"], f) for f in group]}
                          for title, group in cfg["groups"]]}
        for kind, cfg in KINDS.items()
    })


@panel_view(methods=("GET", "POST", "DELETE"))
def crud(request, kind, pk=None):
    cfg = KINDS.get(kind)
    if cfg is None:
        return _err("not_found", 404)
    model, fields = cfg["model"], _fields(kind)
    parent = cfg.get("parent")

    if pk is None and request.method == "GET":
        qs = model.objects.all()
        if parent and request.GET.get(parent):
            qs = qs.filter(**{f"{parent}_id": request.GET[parent]})
        return JsonResponse({"items": [_serialize(kind, o) for o in qs[:300]]})

    obj = None
    if pk is not None:
        obj = model.objects.filter(pk=pk).first()
        if obj is None:
            return _err("not_found", 404)

    if request.method == "GET":
        return JsonResponse(_serialize(kind, obj))

    if request.method == "DELETE":
        obj.delete()
        return JsonResponse({"ok": True})

    # POST: yaratish yoki qisman yangilash — yuborilmagan maydonlar o'zgarmaydi
    if obj is not None:
        # "o'chirish" belgilari validatsiyadan OLDIN (masalan: rasm o'rniga video — ikkalasi birga bo'lmasin)
        for name in fields:
            if request.POST.get(f"clear_{name}") == "1" and name not in request.FILES:
                setattr(obj, name, "")
    Form = _form(model, fields + ([parent] if parent else []))
    if obj:
        data = model_to_dict(obj, fields=Form._meta.fields)
    else:  # yangi yozuv: standart qiymatlar (tartib=0 va h.k.) oldindan
        data = {f.name: f.get_default() for f in model._meta.fields if f.has_default() and f.name in fields}
    data = {k: v for k, v in data.items() if not isinstance(v, FieldFile)}
    data.update(request.POST.dict())
    files = request.FILES
    form = Form(data=data, files=files, instance=obj)
    if obj is not None:
        # Fayl maydonlari: yangisi kelmasa — eskisi qoladi
        for name in fields:
            if isinstance(form.fields.get(name), forms.FileField):
                form.fields[name].required = False
    if not form.is_valid():
        return JsonResponse({"errors": {k: [str(e) for e in v] for k, v in form.errors.items()}}, status=422)
    saved = form.save(commit=False)
    for name in fields:
        if request.POST.get(f"clear_{name}") == "1" and name not in files:
            setattr(saved, name, "")
    saved.save()
    return JsonResponse(_serialize(kind, saved), status=201 if obj is None else 200)


# ---------- xonadonlar (loyiha bo'yicha) ----------

@panel_view()
def flats_overview(request):
    """Loyiha tanlanadi → xonadon turlari (rasmlar shu turga yuklanadi) va xonadonlar ro'yxati."""
    projects = list(Project.objects.order_by("order", "id").values("id", "title"))
    pid = request.GET.get("project")
    project = Project.objects.filter(pk=pid).first() if str(pid).isdigit() else None
    project = project or Project.objects.order_by("order", "id").first()
    if project is None:
        return JsonResponse({"projects": [], "project": None, "types": [], "buildings": [], "flats": []})
    flats = Flat.objects.filter(building__project=project).select_related("building").order_by("building__number", "floor", "number")
    layouts = {(lt.rooms, lt.area): lt for lt in FlatLayout.objects.filter(project=project).prefetch_related("images")}
    groups = flats.values("rooms", "area").annotate(
        total=Count("id"),
        available=Count("id", filter=Q(status=Flat.Status.AVAILABLE)),
        sample=models.Min("id"),
    ).order_by("rooms", "area")
    types = []
    for g in groups:
        lt = layouts.get((g["rooms"], g["area"]))
        imgs = list(lt.images.all()) if lt else []
        sample = Flat.objects.filter(pk=g["sample"]).first()
        types.append({
            "rooms": g["rooms"], "area": float(g["area"]), "areaRaw": str(g["area"]),
            "total": g["total"], "available": g["available"],
            "layout": lt.pk if lt else None, "images": len(imgs),
            "cover": imgs[0].image.url if imgs else (sample.plan.url if sample and sample.plan else None),
            "description": lt.description if lt else "", "sample": g["sample"],
        })
    return JsonResponse({
        "projects": projects, "project": project.pk,
        "types": types,
        "buildings": [{"id": b.pk, "number": b.number} for b in project.buildings.all()],
        "flats": [{"id": f.pk, "number": f.number, "building": f.building.number, "buildingId": f.building_id,
                   "floor": f.floor, "rooms": f.rooms, "area": float(f.area), "status": f.status,
                   "price": f.price, "showPrice": f.show_price} for f in flats],
        "statuses": [{"value": v, "label": l} for v, l in Flat.Status.choices],
    })


@panel_view(methods=("POST",))
def layout_ensure(request):
    """Xonadon turi yozuvi (bo'lmasa — yaratiladi): rasmlar shunga biriktiriladi."""
    d = _body(request)
    project = Project.objects.filter(pk=d.get("project")).first()
    try:
        rooms, area = int(d.get("rooms")), str(d.get("area"))
        layout, _ = FlatLayout.objects.get_or_create(project=project, rooms=rooms, area=area) if project else (None, None)
    except (TypeError, ValueError, ValidationError):
        layout = None
    if layout is None:
        return _err("Noto'g'ri ma'lumot")
    return JsonResponse({"id": layout.pk})
