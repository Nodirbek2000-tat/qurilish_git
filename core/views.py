"""Ommaviy JSON API — Next.js shu yerdan o'qiydi.

GET so'rovlar ochiq (faqat chop etilgan ma'lumot).
POST /api/appeals/ faqat Next.js serveridan (SITE_API_KEY bilan) qabul qilinadi.
"""

import hmac
import ipaddress
import json
import re

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, Q

from .models import (Activity, Appeal, Building, Flat, FlatLayout, Milestone, Post, Project, SalesOffice, SiteSettings,
                     normalize_phone)
from .telegram import notify_appeal
from .uysot import send_lead


def _img(field) -> str | None:
    return field.url if field else None


def _num(value):
    return float(value) if value is not None else None


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def project_brief(p: Project) -> dict:
    return {
        "slug": p.slug,
        "title": p.title,
        "status": p.status,
        "statusLabel": p.get_status_display(),
        "klass": p.get_klass_display(),
        "tagline": p.tagline,
        "address": p.address,
        "color": p.color,
        "cover": _img(p.cover),
        "floors": p.floors,
        "flats": p.flats,
        "area": p.area,
        "handover": p.handover,
        "lat": _num(p.latitude),
        "lng": _num(p.longitude),
        "priceM2": p.price_m2,
    }


def post_brief(p: Post) -> dict:
    return {
        "slug": p.slug,
        "title": p.title,
        "kind": p.kind,
        "kindLabel": p.get_kind_display(),
        "cover": _img(p.cover),
        "excerpt": p.excerpt,
        "date": p.published_at.date().isoformat(),
    }


@require_GET
def site(request):
    s = SiteSettings.load()
    phones = [p.strip() for p in re.split(r"[,;\n]+", s.phone) if p.strip()]
    return JsonResponse({
        "phone": phones[0] if phones else "",
        "phones": phones,
        "email": s.email,
        "address": s.address,
        "lat": _num(s.latitude),
        "lng": _num(s.longitude),
        "workHours": [line for line in s.work_hours.splitlines() if line.strip()],
        "socials": {k: getattr(s, k) for k in ("telegram", "instagram", "facebook", "youtube") if getattr(s, k)},
        "about": {"title": s.about_title, "text": _paragraphs(s.about_text)},
        "stats": {
            "founded": s.founded_year,
            "projects": s.stat_projects,
            "families": s.stat_families,
            "area": s.stat_area,
        },
        "milestones": [{"year": m.year, "title": m.title, "text": m.text, "image": _img(m.image)} for m in Milestone.objects.all()],
        "activities": [{"year": a.year, "organization": a.organization, "title": a.title, "image": _img(a.image)}
                       for a in Activity.objects.all()],
        "offices": [
            {"name": o.name, "address": o.address, "phone": o.phone, "hours": o.hours,
             "lat": _num(o.latitude), "lng": _num(o.longitude), "photo": _img(o.photo)}
            for o in SalesOffice.objects.all()
        ],
    })


@require_GET
def projects(request):
    qs = Project.objects.filter(is_published=True)
    return JsonResponse({"items": [project_brief(p) for p in qs]})


@require_GET
def project_detail(request, slug):
    p = (Project.objects.filter(is_published=True, slug=slug).select_related("office")
         .prefetch_related("images", "arch_items", "interior_slides", "lobby_features", "infra_points", "buildings",
                           "catalog_pages").first())
    if p is None:
        raise Http404
    others = Project.objects.filter(is_published=True).exclude(pk=p.pk)[:3]
    news = p.posts.filter(is_published=True)[:3]
    buildings = list(p.buildings.all())
    o = p.office
    return JsonResponse({
        **project_brief(p),
        "hero": _img(p.hero),
        "logo": _img(p.logo),
        "description": _paragraphs(p.description),
        "features": [f.strip() for f in p.features.splitlines() if f.strip()],
        "about": {
            "image": _img(p.about_image),
            "video": p.about_video.url if p.about_video else None,
            "blocks": p.stat_blocks or len(buildings) or None,
            "queues": p.stat_queues or len({b.queue for b in buildings}) or None,
        },
        "arch": [{"title": a.title, "text": a.text, "image": _img(a.image)} for a in p.arch_items.all()],
        "interior": [{"title": s.title, "text": s.text, "image": s.image.url} for s in p.interior_slides.all()],
        "lobby": {
            "title": p.lobby_title, "text": p.lobby_text, "image": _img(p.lobby_image),
            "features": [{"icon": f.icon, "label": f.label} for f in p.lobby_features.all()],
        },
        "infra": [{"category": i.category, "categoryLabel": i.get_category_display(), "name": i.name,
                   "lat": float(i.latitude), "lng": float(i.longitude)} for i in p.infra_points.all()],
        "office": {"name": o.name, "address": o.address, "phone": o.phone, "hours": o.hours,
                   "lat": _num(o.latitude), "lng": _num(o.longitude), "photo": _img(o.photo)} if o else None,
        "liveUrl": p.live_url if p.live_url.startswith("https://") else "",
        "tourUrl": p.tour_url if p.tour_url.startswith("https://") else "",
        "gallery": [{"src": i.image.url, "caption": i.caption} for i in p.images.all()],
        # Kitobdek varaqlanadigan katalog: sahifalar 1, 2, 3… tartibida, o'lchami bilan (kitob nisbati uchun)
        "catalog": [{"src": c.image.url, "w": c.width, "h": c.height} for c in p.catalog_pages.all() if c.image],
        "others": [project_brief(o) for o in others],
        "news": [post_brief(n) for n in news],
    })


@require_GET
def posts(request):
    qs = Post.objects.filter(is_published=True)
    try:
        limit = max(1, min(int(request.GET.get("limit", 60)), 100))
    except ValueError:
        limit = 60
    return JsonResponse({"items": [post_brief(p) for p in qs[:limit]]})


@require_GET
def post_detail(request, slug):
    p = Post.objects.filter(is_published=True, slug=slug).select_related("project").prefetch_related("images").first()
    if p is None:
        raise Http404
    related = Post.objects.filter(is_published=True).exclude(pk=p.pk)[:3]
    return JsonResponse({
        **post_brief(p),
        "body": _paragraphs(p.body),
        "videoUrl": p.video_url,
        "gallery": [i.image.url for i in p.images.all()],
        "project": {"slug": p.project.slug, "title": p.project.title} if p.project and p.project.is_published else None,
        "related": [post_brief(r) for r in related],
    })


# ---------- xonadonlar ----------

def flat_brief(f: Flat) -> dict:
    b, p = f.building, f.building.project
    return {
        "id": f.id,
        "number": f.number,
        "kind": f.kind,
        "rooms": f.rooms,
        "area": float(f.area),
        "floor": f.floor,
        "status": f.status,
        "statusLabel": f.get_status_display(),
        # Narx: xonadonga alohida narx (ruxsat berilgan bo'lsa), aks holda maydon × loyihaning 1 m² narxi
        "price": f.price if f.show_price and f.price else (round(float(f.area) * p.price_m2) if p.price_m2 else None),
        "priceM2": p.price_m2,
        "plan": _img(f.plan),
        "building": {"id": b.id, "number": b.number, "queue": b.queue},
        "year": b.completion_year,
        "project": {"slug": p.slug, "title": p.title, "color": p.color},
    }


def _int_list(value: str) -> list[int]:
    return [int(x) for x in value.split(",") if x.strip().lstrip("-").isdigit()][:20]


def _float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _flats_base():
    return Flat.objects.filter(building__project__is_published=True).select_related("building__project")


@require_GET
def flats(request):
    """Filtr: project, rooms=1,2,4 (4 = 4+), floor_min/max, area_min/max, year=2027,2028, kind, page."""
    g = request.GET
    available = _flats_base().filter(status=Flat.Status.AVAILABLE)
    qs = available
    if g.get("project"):
        qs = qs.filter(building__project__slug=g["project"][:60])
    if g.get("kind") in Flat.Kind.values:
        qs = qs.filter(kind=g["kind"])
    rooms = _int_list(g.get("rooms", ""))
    if rooms:
        cond = Q(rooms__in=[r for r in rooms if r < 4])
        if any(r >= 4 for r in rooms):
            cond |= Q(rooms__gte=4)
        qs = qs.filter(cond)
    for param, lookup in (("floor_min", "floor__gte"), ("floor_max", "floor__lte"),
                          ("area_min", "area__gte"), ("area_max", "area__lte")):
        v = _float(g.get(param))
        if v is not None:
            qs = qs.filter(**{lookup: v})
    years = _int_list(g.get("year", ""))
    if years:
        qs = qs.filter(building__completion_year__in=years)

    sort = {"area": "area", "-area": "-area", "floor": "floor", "-floor": "-floor"}.get(g.get("sort", ""), None)
    qs = qs.order_by(sort or "-kind", "building__project__order", "floor", "number")  # turar-joy birinchi

    try:
        per = max(1, min(int(g.get("per", 12)), 48))
    except ValueError:
        per = 12
    page = Paginator(qs, per).get_page(g.get("page", 1))

    bounds = available.aggregate(fmin=Min("floor"), fmax=Max("floor"), amin=Min("area"), amax=Max("area"))
    return JsonResponse({
        "items": [flat_brief(f) for f in page.object_list],
        "total": page.paginator.count,
        "page": page.number,
        "pages": page.paginator.num_pages,
        "facets": {
            "floor": [bounds["fmin"] or 1, bounds["fmax"] or 1],
            "area": [float(bounds["amin"] or 0), float(bounds["amax"] or 0)],
            "years": sorted({y for y in available.values_list("building__completion_year", flat=True) if y}),
            "projects": [{"slug": s, "title": t} for s, t in
                         available.values_list("building__project__slug", "building__project__title")
                         .distinct().order_by("building__project__order")],
        },
    })


@require_GET
def flats_by_ids(request):
    ids = _int_list(request.GET.get("ids", ""))
    return JsonResponse({"items": [flat_brief(f) for f in _flats_base().filter(id__in=ids)]})


@require_GET
def flat_detail(request, pk):
    f = _flats_base().filter(pk=pk).first()
    if f is None:
        raise Http404
    b = f.building
    plan = b.floor_plans.filter(floor=f.floor).first()
    same_floor = _flats_base().filter(building=b, floor=f.floor, status=Flat.Status.AVAILABLE).exclude(pk=f.pk)[:6]
    # Shu o'lchamdagi xonadon turi: rasmlar va tavsif panelda bir marta yuklanadi
    layout = FlatLayout.objects.filter(project=b.project, rooms=f.rooms, area=f.area).prefetch_related("images").first()
    return JsonResponse({
        **flat_brief(f),
        "gallery": [{"src": _img(i.image), "caption": i.caption} for i in layout.images.all()] if layout else [],
        "about": _paragraphs(layout.description) if layout else [],
        "parts": layout.parts if layout else [],
        "floorPlan": _img(plan.image) if plan else None,
        "buildingFloors": b.floors,
        "sameFloor": [flat_brief(x) for x in same_floor],
    })


@require_GET
def genplan(request, slug):
    p = Project.objects.filter(is_published=True, slug=slug).first()
    if p is None:
        raise Http404
    buildings = p.buildings.annotate(
        available=Count("flats", filter=Q(flats__status=Flat.Status.AVAILABLE)),
        total=Count("flats"),
    )
    return JsonResponse({
        **project_brief(p),
        "genplan": _img(p.genplan),
        "buildings": [{
            "id": b.id, "number": b.number, "floors": b.floors, "queue": b.queue, "year": b.completion_year,
            "x": float(b.plan_x), "y": float(b.plan_y), "available": b.available, "total": b.total,
        } for b in buildings],
    })


@require_GET
def building(request, pk):
    b = Building.objects.filter(pk=pk, project__is_published=True).select_related("project").first()
    if b is None:
        raise Http404
    per_floor = dict(
        b.flats.filter(status=Flat.Status.AVAILABLE).values("floor").annotate(n=Count("id")).values_list("floor", "n")
    )
    floors = sorted(set(b.flats.values_list("floor", flat=True)) | set(range(1, b.floors + 1)), reverse=True)
    try:
        floor = int(request.GET.get("floor", ""))
    except ValueError:
        floor = None
    if floor not in floors:
        floor = next((f for f in sorted(floors) if per_floor.get(f)), floors[-1] if floors else 1)
    plan = b.floor_plans.filter(floor=floor).first()
    return JsonResponse({
        "id": b.id, "number": b.number, "queue": b.queue, "year": b.completion_year,
        "project": project_brief(b.project),
        "siblings": list(b.project.buildings.values_list("id", "number")),
        "floors": [{"floor": f, "available": per_floor.get(f, 0)} for f in floors],
        "floor": floor,
        "floorPlan": _img(plan.image) if plan else None,
        "flats": [flat_brief(f) for f in _flats_base().filter(building=b, floor=floor)],
    })


def _check_site_key(request):
    return hmac.compare_digest(request.headers.get("X-Site-Key", ""), settings.SITE_API_KEY)


def _json_body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _rate_limited(request, scope: str) -> bool:
    ip = str(request.headers.get("X-Client-IP", ""))[:64] or "unknown"
    key = f"{scope}-rate:{ip}"
    count = cache.get(key) or 0
    if count >= RATE_LIMIT:
        return True
    cache.set(key, count + 1, RATE_WINDOW)
    return False


# ---------- murojaat qabul qilish ----------

PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{9,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LIMITS = {"name": 120, "phone": 32, "email": 254, "subject": 200, "message": 3000,
          "company": 200, "inn": 20, "doc_number": 60}
SUSPECT_NOTE = "Bot bo'lishi mumkin: formadagi yashirin maydon to'ldirilgan"
RATE_LIMIT = 5          # bir IP dan
RATE_WINDOW = 10 * 60   # 10 daqiqada
# Ariza: bitta odam (IP yoki telefon) 24 soatda ko'pi bilan 3 ta
DAY_LIMIT = 3
DAY_WINDOW = 24 * 60 * 60
# Ismda bo'lmaydigan belgilar — skaner botlar shunday "ism" yuboradi: echo $(...), {{this}}, ||, <script>
NAME_BAD = re.compile(r"[<>{}\[\]$|;&\\/=*#%@^~_0-9]")


def _client_ip(request) -> str | None:
    raw = str(request.headers.get("X-Client-IP", "")).strip()[:64]
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


@csrf_exempt  # brauzer emas, Next.js serveri yuboradi; himoya — SITE_API_KEY
@require_POST
def create_appeal(request):
    key = request.headers.get("X-Site-Key", "")
    if not hmac.compare_digest(key, settings.SITE_API_KEY):
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "bad_json"}, status=400)

    ip = _client_ip(request)
    ip_key = f"appeal-day-ip:{ip or 'unknown'}"
    if (cache.get(ip_key) or 0) >= DAY_LIMIT:
        return JsonResponse({"error": "rate_limited"}, status=429)

    clean = {k: str(data.get(k, "")).strip()[:limit] for k, limit in LIMITS.items()}
    errors = {}
    if len(clean["name"]) < 2 or NAME_BAD.search(clean["name"]):
        errors["name"] = "Ismingizni kiriting"
    # Saytdagi barcha formalar +998 bilan — boshqa raqam (555-666-0606 kabi) — bot
    phone = normalize_phone(clean["phone"]) if PHONE_RE.match(clean["phone"]) else ""
    if not phone:
        errors["phone"] = "Telefon raqam noto'g'ri"
    if clean["email"] and not EMAIL_RE.match(clean["email"]):
        errors["email"] = "Email noto'g'ri"
    kind = data.get("kind") if data.get("kind") in Appeal.Kind.values else Appeal.Kind.APPEAL
    if kind == Appeal.Kind.APPEAL and len(clean["message"]) < 5:
        errors["message"] = "Xabar matnini yozing"
    source = data.get("source") if data.get("source") in Appeal.Source.values else ""
    applicant = data.get("applicant") if data.get("applicant") in Appeal.Applicant.values else Appeal.Applicant.PERSON
    if applicant == Appeal.Applicant.COMPANY:
        if len(clean["company"]) < 2:
            errors["company"] = "Kompaniya nomini kiriting"
        if not re.fullmatch(r"\d{9}", clean["inn"]):
            errors["inn"] = "STIR 9 xonali raqam bo'lsin"
        # Kompaniya uchun hamma maydon majburiy
        if not clean["email"]:
            errors["email"] = "Elektron pochtani kiriting"
        if not clean["doc_number"]:
            errors["doc_number"] = "Hujjat raqamini kiriting"
        if len(clean["subject"]) < 2:
            errors["subject"] = "Murojaat mavzusini kiriting"
    else:
        clean["company"] = clean["inn"] = ""
    if errors:
        return JsonResponse({"errors": errors}, status=422)

    project = None
    if data.get("project"):
        project = Project.objects.filter(slug=str(data["project"])[:60], is_published=True).first()
    flat = None
    if str(data.get("flat", "")).isdigit():
        flat = Flat.objects.filter(pk=int(data["flat"])).select_related("building__project").first()
        project = project or (flat.building.project if flat else None)

    phone_key = f"appeal-day-phone:{phone}"
    if (cache.get(phone_key) or 0) >= DAY_LIMIT:
        return JsonResponse({"error": "rate_limited"}, status=429)

    # Yashirin tuzoq to'ldirilgan (bot yoki brauzer avtoto'ldirishi) — panelda saqlanadi, lekin
    # Telegram va CRM'ga yuborilmaydi (botlar u yerni to'ldirib tashlamasin)
    suspect = data.get("suspect") == "1"
    appeal = Appeal.objects.create(kind=kind, source=source, applicant=applicant, project=project, flat=flat,
                                   country=str(data.get("country", "")).strip()[:80],
                                   note=SUSPECT_NOTE if suspect else "", ip=ip,
                                   user_agent=str(request.headers.get("X-Client-UA", ""))[:300], **clean)
    if not suspect:
        notify_appeal(appeal)
        send_lead(appeal)
    for k in (ip_key, phone_key):
        cache.set(k, (cache.get(k) or 0) + 1, DAY_WINDOW)
    return JsonResponse({"ok": True}, status=201)
