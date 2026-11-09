"""Saytdagi (Next.js) keshni darhol yangilash: manage.py kesh_yangila

Serverga yangi versiya chiqarilgandan keyin deploy.sh o'zi chaqiradi."""

from django.core.management.base import BaseCommand

from core.signals import _send

TAGS = ["site", "projects", "posts", "flats"]


class Command(BaseCommand):
    help = "Next.js sayt keshini yangilaydi (barcha teglar)"

    def handle(self, *args, **options):
        _send(TAGS)
        self.stdout.write("Kesh yangilandi: " + ", ".join(TAGS))
