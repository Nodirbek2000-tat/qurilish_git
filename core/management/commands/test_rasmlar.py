"""FAQAT LOKAL SINOV: `_test_rasmlar/` dagi rasmlarni loyiha, galereya, reja va yangiliklarga biriktiradi.

    python manage.py test_rasmlar            # qo'yish
    python manage.py test_rasmlar --ochirish # hammasini olib tashlash (DEPLOYDAN OLDIN SHART!)

Bu rasmlar boshqa kompaniyaga tegishli — serverga chiqmasligi kerak.
Hammasi MEDIA_ROOT/test/ ichida turadi, shuning uchun bitta buyruq bilan izsiz o'chadi.
"""

import json
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import ArchItem, Flat, InteriorSlide, Post, PostImage, Project, ProjectImage
from core.signals import _send

SRC = settings.BASE_DIR / "_test_rasmlar"
DST = settings.MEDIA_ROOT / "test"


INTERIOR = [
    ("Mehmonxona", "Keng, yorug' xonalar: panoramali oynalar va baland shift har bir kunni bayram qiladi."),
    ("Oshxona-ovqatlanish zonasi", "Oila davrasidagi kechki ovqat uchun puxta o'ylangan maydon."),
    ("Bolalar xonasi", "Xavfsiz materiallar va o'yin uchun erkin maydon."),
    ("Dam olish zonasi", "Kun oxirida tinchlik va qulaylik."),
]


def _file(url: str) -> str:
    return url.rsplit("/", 1)[1]


class Command(BaseCommand):
    help = "Lokal sinov rasmlarini qo'yadi yoki --ochirish bilan olib tashlaydi"

    def add_arguments(self, parser):
        parser.add_argument("--ochirish", action="store_true")

    def handle(self, *args, ochirish, **opts):
        if ochirish:
            return self.remove()
        if not settings.DEBUG:
            raise CommandError("Test rasmlari faqat lokal (DEBUG=1) rejimda qo'yiladi.")
        manifest = json.loads((SRC / "manifest.json").read_text())
        DST.mkdir(parents=True, exist_ok=True)

        def put(url: str) -> str:
            name = _file(url)
            shutil.copy2(SRC / name, DST / name)
            return f"test/{name}"

        with transaction.atomic():
            for slug, imgs in manifest["projects"].items():
                p = Project.objects.filter(slug=slug).first()
                if not p:
                    continue
                g = imgs["gallery"]  # 0-1 tashqi ko'rinish, 2-5 interyer, 6 lobbi (bo'lsa)
                Project.objects.filter(pk=p.pk).update(
                    cover=put(imgs["cover"]), hero=put(imgs["cover"]), about_image=put(g[-1]),
                    lobby_image=put(g[6] if len(g) > 6 else g[-1]))
                for item, url in zip(p.arch_items.all(), [g[0], g[1], imgs["cover"]]):
                    ArchItem.objects.filter(pk=item.pk).update(image=put(url))
                InteriorSlide.objects.filter(project=p).delete()
                InteriorSlide.objects.bulk_create(
                    InteriorSlide(project=p, title=t, text=x, image=put(u), order=i)
                    for i, ((t, x), u) in enumerate(zip(INTERIOR, g[2:6])))
                ProjectImage.objects.filter(project=p, image__startswith="test/").delete()
                ProjectImage.objects.bulk_create(
                    ProjectImage(project=p, image=put(u), order=i) for i, u in enumerate(g))
            for post, url in zip(Post.objects.order_by("-published_at"), manifest["posts"]):
                Post.objects.filter(pk=post.pk).update(cover=put(url))
            for rooms, url in manifest["plans"].items():
                qs = Flat.objects.filter(kind=Flat.Kind.RESIDENTIAL)
                qs = qs.filter(rooms__gte=4) if rooms == "4" else qs.filter(rooms=int(rooms))
                qs.update(plan=put(url))

        _send(["projects", "posts", "flats"])
        self.stdout.write(self.style.WARNING(
            "Test rasmlari qo'yildi. Serverga chiqishdan oldin: python manage.py test_rasmlar --ochirish"))

    def remove(self):
        with transaction.atomic():
            Project.objects.filter(cover__startswith="test/").update(cover="")
            Project.objects.filter(hero__startswith="test/").update(hero="")
            Project.objects.filter(about_image__startswith="test/").update(about_image="")
            Project.objects.filter(lobby_image__startswith="test/").update(lobby_image="")
            ArchItem.objects.filter(image__startswith="test/").update(image="")
            InteriorSlide.objects.filter(image__startswith="test/").delete()
            Post.objects.filter(cover__startswith="test/").update(cover="")
            Flat.objects.filter(plan__startswith="test/").update(plan="")
            ProjectImage.objects.filter(image__startswith="test/").delete()
            PostImage.objects.filter(image__startswith="test/").delete()
        shutil.rmtree(DST, ignore_errors=True)
        _send(["projects", "posts", "flats"])
        self.stdout.write(self.style.SUCCESS("Test rasmlari to'liq olib tashlandi."))
