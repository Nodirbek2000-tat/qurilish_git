"""Panel uchun akkaunt yaratadi.

Parol tasodifiy yaratiladi va faqat PANEL_KIRISH.txt fayliga yoziladi —
ekranga chiqmaydi. Birinchi kirishdan keyin faylni o'chiring.

    python manage.py create_panel_user --username admin
"""

import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import TwoFactor


class Command(BaseCommand):
    help = "Panel akkauntini yaratadi (parol PANEL_KIRISH.txt ga yoziladi)"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="arxan_admin")
        parser.add_argument("--reset", action="store_true", help="Mavjud akkaunt parolini va 2FA ni yangilash")

    def handle(self, *args, username, reset, **opts):
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if user and not reset:
            raise CommandError(f"'{username}' allaqachon bor. Yangilash uchun --reset qo'shing.")

        password = secrets.token_urlsafe(18)
        if user is None:
            user = User.objects.create_superuser(username=username, email="", password=password)
        else:
            user.set_password(password)
            user.is_active = user.is_staff = user.is_superuser = True
            user.save()
            TwoFactor.objects.filter(user=user).delete()

        out = settings.BASE_DIR / "PANEL_KIRISH.txt"
        out.write_text(
            "ARXAN PANEL — KIRISH MA'LUMOTLARI\n"
            "==================================\n"
            f"Manzil (dev):  http://127.0.0.1:8000/{settings.PANEL_PATH}/\n"
            f"Login:         {username}\n"
            f"Parol:         {password}\n\n"
            "Birinchi kirishda telefoningizdagi Google/Microsoft Authenticator bilan\n"
            "QR kodni skanerlaysiz — keyin har safar ilovadagi 6 xonali kod so'raladi.\n\n"
            "MUHIM: kirgandan keyin parolni panelda o'zgartiring va bu faylni o'chiring.\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"Akkaunt tayyor. Ma'lumotlar: {out}"))
