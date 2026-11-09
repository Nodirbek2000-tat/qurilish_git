"""Panel sayti va kirish.

1-bosqich: login + parol.  2-bosqich (settings.PANEL_TWO_FACTOR yoqilgan bo'lsa): autentifikator kodi.
Kerakli bosqichlar o'tmaguncha panelning hech bir sahifasi ochilmaydi.
"""

import time

import segno
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import authenticate, get_user_model, login
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from unfold.sites import UnfoldAdminSite

from . import totp
from .models import TwoFactor

OTP_SESSION_KEY = "panel_otp_ok"
PENDING_KEY = "panel_pending_uid"
PENDING_TS = "panel_pending_ts"
PENDING_TTL = 5 * 60  # parol to'g'ri kiritilgandan keyin kodga 5 daqiqa

MAX_FAILS = 5
LOCK_SECONDS = 15 * 60


class PanelSite(UnfoldAdminSite):
    site_header = "ARXAN"
    site_title = "Arxan panel"
    index_title = "Boshqaruv paneli"

    def has_permission(self, request):
        return super().has_permission(request) and request.session.get(OTP_SESSION_KEY) is True

    def login(self, request, extra_context=None):
        return redirect("panel_login")


# ---------- urinishlarni cheklash ----------

def client_ip(request) -> str:
    # Faqat ishonchli proksi (nginx) orqasida X-Real-IP ga ishonamiz
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "")


def _keys(request, username: str = "") -> list[str]:
    keys = [f"panel-fail-ip:{client_ip(request)}"]
    if username:
        keys.append(f"panel-fail-user:{username.lower()[:150]}")
    return keys


def is_locked(request, username: str = "") -> bool:
    return any((cache.get(k) or 0) >= MAX_FAILS for k in _keys(request, username))


def register_fail(request, username: str = "") -> None:
    for k in _keys(request, username):
        cache.set(k, (cache.get(k) or 0) + 1, LOCK_SECONDS)


def clear_fails(request, username: str = "") -> None:
    cache.delete_many(_keys(request, username))


# ---------- ko'rinishlar ----------

LOCKED_MSG = "Juda ko'p noto'g'ri urinish. 15 daqiqadan keyin qayta urinib ko'ring."


@method_decorator([never_cache, csrf_protect, sensitive_post_parameters("password")], name="dispatch")
class PasswordStepView(View):
    template = "panel/login.html"

    def get(self, request):
        if admin.site.has_permission(request):
            return redirect("admin:index")
        return render(request, self.template)

    def post(self, request):
        username = request.POST.get("username", "").strip()[:150]
        password = request.POST.get("password", "")
        ctx = {"username": username}

        if request.POST.get("website"):  # bot tuzog'i
            return render(request, self.template, ctx, status=400)
        if is_locked(request, username):
            return render(request, self.template, {**ctx, "error": LOCKED_MSG}, status=429)

        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active or not user.is_staff:
            register_fail(request, username)
            time.sleep(0.4)
            return render(request, self.template, {**ctx, "error": "Login yoki parol noto'g'ri."}, status=401)

        if not settings.PANEL_TWO_FACTOR:  # 2-bosqich o'chiq — parol to'g'ri bo'lsa darhol kiradi
            clear_fails(request, username)
            login(request, user)  # sessiya kaliti shu yerda yangilanadi
            request.session[OTP_SESSION_KEY] = True
            return redirect(reverse("admin:index"))

        request.session.cycle_key()
        request.session[PENDING_KEY] = user.pk
        request.session[PENDING_TS] = int(time.time())
        return redirect("panel_code")


@method_decorator([never_cache, csrf_protect], name="dispatch")
class CodeStepView(View):
    template = "panel/code.html"

    def _pending_user(self, request):
        uid = request.session.get(PENDING_KEY)
        ts = request.session.get(PENDING_TS, 0)
        if not uid or time.time() - ts > PENDING_TTL:
            return None
        return get_user_model().objects.filter(pk=uid, is_active=True, is_staff=True).first()

    def _context(self, user, device, **extra):
        ctx = {"setup": not device.confirmed, **extra}
        if not device.confirmed:
            uri = totp.provisioning_uri(device.secret, user.get_username())
            ctx["qr_svg"] = segno.make(uri, error="m").svg_inline(scale=5, dark="#111315", light="#ffffff")
            ctx["secret"] = " ".join(device.secret[i:i + 4] for i in range(0, len(device.secret), 4))
        return ctx

    def get(self, request):
        user = self._pending_user(request)
        if user is None:
            return redirect("panel_login")
        device, _ = TwoFactor.objects.get_or_create(user=user, defaults={"secret": totp.new_secret()})
        return render(request, self.template, self._context(user, device))

    def post(self, request):
        user = self._pending_user(request)
        if user is None:
            return redirect("panel_login")
        username = user.get_username()
        device, _ = TwoFactor.objects.get_or_create(user=user, defaults={"secret": totp.new_secret()})

        if is_locked(request, username):
            request.session.flush()
            return render(request, "panel/login.html", {"error": LOCKED_MSG}, status=429)

        step = totp.verify(device.secret, request.POST.get("code", ""), device.last_step)
        if step is None:
            register_fail(request, username)
            return render(request, self.template,
                          self._context(user, device, error="Kod noto'g'ri yoki eskirgan."), status=401)

        device.last_step = step
        device.confirmed = True
        device.save(update_fields=["last_step", "confirmed"])
        clear_fails(request, username)

        login(request, user)  # sessiya kaliti shu yerda yangilanadi
        request.session.pop(PENDING_KEY, None)
        request.session.pop(PENDING_TS, None)
        request.session[OTP_SESSION_KEY] = True
        return redirect(reverse("admin:index"))
