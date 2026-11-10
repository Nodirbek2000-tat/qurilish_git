"""Saytdan kelgan arizani Uysot CRM'ga yuborish (sotuv bo'limi lidlarni o'sha yerda ko'radi).

Hujjat: POST https://service.app.uysot.uz/v1/external-source, sarlavha X-Auth: <token>, JSON tana.
Sozlamalar .env da: UYSOT_TOKEN (bo'sh bo'lsa — hech narsa yuborilmaydi).
Uysot ishlamasa ham ariza bazada, panelda va Telegramda bo'ladi.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request

from django.conf import settings

from .models import normalize_phone
from .telegram import category

log = logging.getLogger(__name__)
ATTEMPTS = 3


def lead_payload(a) -> dict:
    """Uysot formatidagi lid: telefon majburiy, qolgani — menejerga foydali izoh."""
    notes = [f"Saytdan: {category(a)}"]
    if a.flat:
        f = a.flat
        notes.append(f"Xonadon: {f.building.number}-blok, №{f.number} · {f.rooms} xonali, {f.area} m², {f.floor}-qavat")
    if a.company:
        notes.append(f"Kompaniya: {a.company} (STIR {a.inn})")
    if a.email:
        notes.append(f"Email: {a.email}")
    if a.subject:
        notes.append(f"Mavzu: {a.subject}")
    if a.message:
        notes.append(a.message)
    data = {
        "phoneNumber": normalize_phone(a.phone) or a.phone,
        "name": a.name,
        "message": "\n".join(notes)[:2000],
        "tagList": settings.UYSOT_TAGS,
        "houseName": a.project.title if a.project else settings.UYSOT_HOUSE,
        "esType": "WEBSITE",
    }
    return {k: v for k, v in data.items() if v}


# Uysot oldida Cloudflare turadi: "Python-urllib" nomini bloklaydi (403, error code 1010).
# O'zimizni ochiq tanishtiramiz; baribir bloklansa — Uysot server IP'mizni ruxsat ro'yxatiga qo'shadi.
USER_AGENT = "ArxanSite/1.0 (+https://arxan.uz; Uysot integratsiyasi)"


def _post(payload: dict) -> int | None:
    """Yuboradi va javob kodini qaytaradi (200/201 — qabul qilindi). Tekshirish uchun qo'lda ham chaqirsa bo'ladi."""
    body = json.dumps(payload, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "X-Auth": settings.UYSOT_TOKEN, "User-Agent": USER_AGENT}
    for attempt in range(1, ATTEMPTS + 1):
        req = urllib.request.Request(settings.UYSOT_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                log.info("Uysot: lid qabul qilindi (%s) %s", resp.status, payload.get("phoneNumber"))
                return resp.status
        except urllib.error.HTTPError as exc:  # Uysot rad etdi (token, format) — qayta urinish foydasiz
            log.warning("Uysot rad etdi: %s %s", exc.code, exc.read()[:300])
            return exc.code
        except Exception as exc:  # tarmoq uzilishi — biroz kutib qayta
            if attempt == ATTEMPTS:
                log.warning("Uysot'ga yuborib bo'lmadi: %s", exc)
            else:
                time.sleep(2 * attempt)
    return None


def send_lead(appeal, suspect: bool = False) -> None:
    # Token yo'q (lokal) yoki bot to'ldirgan forma — CRM'ga yuborilmaydi
    if not settings.UYSOT_TOKEN or suspect:
        return
    threading.Thread(target=_post, args=(lead_payload(appeal),), daemon=True).start()
