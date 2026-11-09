"""FAQAT LOKAL SINOV UCHUN: panelning 2-bosqich kodini terminalda ko'rsatadi.

    python manage.py panel_code arxan_admin

Telefon/QR kerak bo'lmaydi. Kod 30 soniya amal qiladi.
DEBUG=0 (production) da ishlamaydi — u yerda faqat autentifikator ilovasi.
"""

import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core import totp
from core.models import TwoFactor


class Command(BaseCommand):
    help = "Lokal sinov uchun joriy 2FA kodini chiqaradi (faqat DEBUG=1)"

    def add_arguments(self, parser):
        parser.add_argument("username", nargs="?", default="arxan_admin")

    def handle(self, *args, username, **opts):
        if not settings.DEBUG:
            raise CommandError("Bu buyruq faqat DEBUG=1 (lokal) rejimda ishlaydi.")
        user = get_user_model().objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"'{username}' topilmadi")
        device, _ = TwoFactor.objects.get_or_create(user=user, defaults={"secret": totp.new_secret()})
        step = int(time.time()) // totp.STEP
        left = totp.STEP - int(time.time()) % totp.STEP
        self.stdout.write(self.style.SUCCESS(f"Kod: {totp._code(device.secret, step)}") + f"  ({left} soniya amal qiladi)")
