"""Telegram bot (qurilish_bot) uchun API — panelga kirish va /admin.

Faqat bot chaqiradi: X-Bot-Key sarlavhasi settings.BOT_API_KEY bilan bir xil bo'lishi shart.
Bot o'zi hech narsani hal qilmaydi: kimga ruxsat borligini faqat shu yerda (katta bazada) tekshiramiz.
"""

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import PanelAccess, PanelLoginEvent, PanelLoginLink, normalize_phone

Event = PanelLoginEvent.Kind


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _err(msg, status=400):
    return JsonResponse({"error": msg}, status=status)


def _tid(value):
    try:
        tid = int(value)
    except (TypeError, ValueError):
        return None
    return tid if tid > 0 else None


def bot_view(admin=False):
    """Kalitni tekshiradi; admin=True bo'lsa — so'rovchi (actor) bazada admin bo'lishi shart."""
    def deco(fn):
        @csrf_exempt
        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            key = settings.BOT_API_KEY
            if not key or not hmac.compare_digest(request.headers.get("X-Bot-Key", ""), key):
                return _err("forbidden", 403)
            if request.method != "POST":
                return _err("method", 405)
            try:
                data = json.loads(request.body or b"{}")
            except ValueError:
                return _err("bad_json")
            if not isinstance(data, dict):
                return _err("bad_json")
            request.data = data
            if admin:
                tid = _tid(data.get("actor"))
                actor = PanelAccess.objects.filter(telegram_id=tid, role=PanelAccess.Role.ADMIN).first() if tid else None
                if actor is None:
                    return _err("not_admin", 403)
                request.actor = actor
            return fn(request, *args, **kwargs)
        return wrapper
    return deco


def _item(a: PanelAccess) -> dict:
    return {"id": a.pk, "name": a.full_name, "phone": a.phone, "role": a.role, "linked": a.telegram_id is not None,
            "lastLogin": timezone.localtime(a.last_login_at).strftime("%d.%m.%Y %H:%M") if a.last_login_at else None}


# ---------- kirish ----------

@bot_view()
def contact(request):
    """Foydalanuvchi o'z raqamini yubordi: ruxsat bo'lsa — Telegram ID shu raqamga bog'lanadi."""
    d = request.data
    tid, phone, name = _tid(d.get("telegram_id")), normalize_phone(d.get("phone", "")), str(d.get("name", ""))[:120]
    if tid is None or not phone:
        return _err("bad_phone")
    access = PanelAccess.objects.filter(phone=phone).first()
    if access is None:
        PanelLoginEvent.objects.create(kind=Event.DENIED, phone=phone, telegram_id=tid, name=name)
        return _err("denied", 403)
    with transaction.atomic():
        # Bitta Telegram — bitta ruxsat (raqam almashtirilgan bo'lsa eski bog'lanish uziladi)
        PanelAccess.objects.filter(telegram_id=tid).exclude(pk=access.pk).update(telegram_id=None)
        access.telegram_id = tid
        access.save(update_fields=["telegram_id"])
    PanelLoginEvent.objects.create(kind=Event.REQUEST, access=access, phone=phone, telegram_id=tid, name=name)
    return JsonResponse({"name": access.full_name, "role": access.role})


@bot_view()
def me(request):
    tid = _tid(request.data.get("telegram_id"))
    access = PanelAccess.objects.filter(telegram_id=tid).first() if tid else None
    if access is None:
        return _err("unknown", 404)
    return JsonResponse({"name": access.full_name, "role": access.role})


@bot_view()
def link(request):
    """Bir martalik kirish havolasi. Bazada token o'zi emas, faqat hash'i saqlanadi."""
    tid = _tid(request.data.get("telegram_id"))
    access = PanelAccess.objects.filter(telegram_id=tid).first() if tid else None
    if access is None:
        return _err("unknown", 403)
    now = timezone.now()
    PanelLoginLink.objects.filter(access=access, used_at__isnull=True).delete()  # eski havolalar kuchini yo'qotadi
    PanelLoginLink.objects.filter(expires_at__lt=now - timedelta(days=1)).delete()  # eskirganlarni tozalash
    token = secrets.token_urlsafe(32)
    PanelLoginLink.objects.create(access=access, token_hash=token_hash(token),
                                  expires_at=now + timedelta(seconds=settings.PANEL_LINK_AGE))
    PanelLoginEvent.objects.create(kind=Event.LINK, access=access, phone=access.phone, telegram_id=tid)
    return JsonResponse({"url": f"{settings.PANEL_LOGIN_URL}?t={token}", "minutes": settings.PANEL_LINK_AGE // 60})


# ---------- /admin ----------

@bot_view(admin=True)
def stats(request):
    ev = PanelLoginEvent.objects
    asked = ev.filter(kind__in=[Event.REQUEST, Event.DENIED])
    logins = ev.filter(kind=Event.LOGIN)
    roles = dict(PanelAccess.objects.values_list("role").annotate(n=Count("id")))
    recent = [{"name": e.access.full_name if e.access else e.phone, "phone": e.phone,
               "at": timezone.localtime(e.created_at).strftime("%d.%m.%Y %H:%M"), "ip": e.ip}
              for e in logins.select_related("access")[:5]]
    return JsonResponse({
        "requests": asked.count(),
        "requestPeople": asked.values("telegram_id").distinct().count(),
        "deniedPeople": ev.filter(kind=Event.DENIED).values("telegram_id").distinct().count(),
        "logins": logins.count(),
        "loginPeople": logins.values("access").distinct().count(),
        "admins": roles.get(PanelAccess.Role.ADMIN, 0),
        "staff": roles.get(PanelAccess.Role.STAFF, 0),
        "recent": recent,
    })


@bot_view(admin=True)
def access_list(request):
    return JsonResponse({"items": [_item(a) for a in PanelAccess.objects.all()], "me": request.actor.pk})


@bot_view(admin=True)
def access_add(request):
    d = request.data
    name, phone, role = " ".join(str(d.get("name", "")).split())[:120], normalize_phone(d.get("phone", "")), d.get("role")
    if len(name) < 3:
        return _err("Ism-familiyani to'liq yozing")
    if not phone:
        return _err("Raqam noto'g'ri. Masalan: +998901234567")
    if role not in PanelAccess.Role.values:
        return _err("Huquq noto'g'ri")
    existing = PanelAccess.objects.filter(phone=phone).first()
    if existing:
        return _err(f"Bu raqam allaqachon ro'yxatda: {existing.full_name}")
    access = PanelAccess.objects.create(full_name=name, phone=phone, role=role, added_by=request.actor)
    return JsonResponse(_item(access), status=201)


@bot_view(admin=True)
def access_delete(request):
    access = PanelAccess.objects.filter(pk=_tid(request.data.get("id"))).first()
    if access is None:
        return _err("Topilmadi", 404)
    if access.pk == request.actor.pk:
        return _err("O'zingizni o'chira olmaysiz")
    access.delete()
    return JsonResponse({"ok": True})


# ---------- panelga kirish (Next serveri chaqiradi, panel_api orqali) ----------

def use_link(token: str, ip: str = ""):
    """Havolani bir marta ishlatadi; yaroqli bo'lsa — PanelAccess, aks holda None."""
    if not token or len(token) > 100:
        return None
    now = timezone.now()
    link = PanelLoginLink.objects.select_related("access__user").filter(token_hash=token_hash(token)).first()
    if link is None or link.expires_at < now or link.access.user is None or not link.access.user.is_active:
        return None
    # Bir vaqtda ikki marta bosilsa ham faqat bittasi o'tadi
    if PanelLoginLink.objects.filter(pk=link.pk, used_at__isnull=True).update(used_at=now) != 1:
        return None
    access = link.access
    access.last_login_at = now
    access.save(update_fields=["last_login_at"])
    PanelLoginEvent.objects.create(kind=Event.LOGIN, access=access, phone=access.phone,
                                   telegram_id=access.telegram_id, ip=ip[:64])
    return access
