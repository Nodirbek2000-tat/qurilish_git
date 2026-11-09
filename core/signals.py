"""Panelda biror narsa o'zgarsa, Next.js keshini darhol yangilash."""

import json
import logging
import threading
import urllib.request

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import (Activity, ArchItem, Building, CatalogPage, Flat, FlatLayout, FlatLayoutImage, FloorPlan, InfraPoint, InteriorSlide, LobbyFeature, Milestone, Post,
                     PostImage, Project, ProjectImage, SalesOffice, SiteSettings)

log = logging.getLogger(__name__)

TAGS = {
    Project: ["projects", "flats"],
    ProjectImage: ["projects"],
    CatalogPage: ["projects"],
    ArchItem: ["projects"],
    InteriorSlide: ["projects"],
    LobbyFeature: ["projects"],
    InfraPoint: ["projects"],
    Building: ["flats"],
    FloorPlan: ["flats"],
    Flat: ["flats"],
    FlatLayout: ["flats"],
    FlatLayoutImage: ["flats"],
    Post: ["posts", "projects"],
    PostImage: ["posts"],
    SiteSettings: ["site"],
    Milestone: ["site"],
    Activity: ["site"],
    SalesOffice: ["site", "projects"],
}


def _send(tags: list[str]) -> None:
    url, secret = settings.NEXT_REVALIDATE_URL, settings.NEXT_REVALIDATE_SECRET
    if not url or not secret:
        return
    req = urllib.request.Request(
        url,
        data=json.dumps({"tags": tags}).encode(),
        headers={"Content-Type": "application/json", "X-Revalidate-Secret": secret},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15).close()  # fon oqimida — panelni kuttirmaydi; dev'da Next kompilyatsiyasiga yetadi
    except Exception as exc:  # sayt o'chiq bo'lsa ham panel ishlayversin
        log.warning("Next.js keshini yangilab bo'lmadi: %s", exc)


_pending = threading.local()


def _flush():
    tags = sorted(getattr(_pending, "tags", set()))
    _pending.tags = set()
    if tags:
        threading.Thread(target=_send, args=(tags,), daemon=True).start()


@receiver([post_save, post_delete])
def revalidate(sender, **kwargs):
    tags = TAGS.get(sender)
    if not tags:
        return
    # Bir tranzaksiyada 100 ta xonadon o'zgarsa ham — bitta so'rov
    if not getattr(_pending, "tags", None):
        _pending.tags = set()
        transaction.on_commit(_flush)
    _pending.tags.update(tags)
