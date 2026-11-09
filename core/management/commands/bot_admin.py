"""Birinchi adminni qo'shish (keyingilarini u botdagi /admin orqali qo'shadi).

    python manage.py bot_admin "Ism Familiya" +998901234567
"""

from django.core.management.base import BaseCommand, CommandError

from core.models import PanelAccess, normalize_phone


class Command(BaseCommand):
    help = "Telefon raqamga admin huquqini beradi (panel + botdagi /admin)"

    def add_arguments(self, parser):
        parser.add_argument("name", help="Ism-familiya")
        parser.add_argument("phone", help="+998901234567")

    def handle(self, name, phone, **opts):
        phone = normalize_phone(phone)
        if not phone:
            raise CommandError("Raqam noto'g'ri. Masalan: +998901234567")
        access, created = PanelAccess.objects.get_or_create(phone=phone, defaults={"full_name": name})
        access.full_name, access.role = name, PanelAccess.Role.ADMIN
        access.save()
        verb = "Qo'shildi" if created else "Yangilandi"
        self.stdout.write(self.style.SUCCESS(f"{verb}: {access} - admin"))
        self.stdout.write("Endi Telegram'da botga /start bosing va raqamingizni yuboring.")
