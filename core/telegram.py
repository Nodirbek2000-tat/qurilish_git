"""Saytdan kelgan yangi murojaat haqida Telegram botga xabar yuborish.

Sozlamalar .env da: TELEGRAM_BOT_TOKEN va TELEGRAM_CHAT_ID (bir nechta bo'lsa — vergul bilan).
"""

import html
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)


def category(a) -> str:
    """Saytning qaysi formasidan kelgani: «Loyiha: Arxan Residence», «Murojaat · Kompaniya», «Aloqa»…"""
    if a.source == a.Source.PROJECT and a.project:
        return f"Loyiha: {a.project.title}"
    if a.source == a.Source.APPEAL:
        return f"Murojaat · {a.get_applicant_display()}"
    return a.get_source_display() if a.source else a.get_kind_display()


def appeal_text(a, suspect: bool = False) -> str:
    e = lambda s: html.escape(s, quote=False)  # o' va g' dagi apostrof o'z holicha qoladi
    rows = ["🆕 <b>Yangi murojaat</b>", f"📂 {e(category(a))}", ""]
    if suspect:
        rows[2:2] = ["⚠️ Bot bo'lishi mumkin (yashirin maydon to'ldirilgan)"]
    if a.company:
        rows.append(f"🏛 {e(a.company)} · STIR {e(a.inn)}")
    rows += [f"👤 {e(a.name)}", f"📞 {e(a.phone)}"]
    if a.email:
        rows.append(f"✉️ {e(a.email)}")
    if a.country:
        rows.append(f"🌍 {e(a.country)}")
    if a.project and a.source != a.Source.PROJECT:
        rows.append(f"🏢 {e(a.project.title)}")
    if a.flat:
        f = a.flat
        rows.append(f"🚪 {f.building.number}-blok, №{e(f.number)} · {f.rooms} xonali, {f.area} m², {f.floor}-qavat")
    if a.doc_number:
        rows.append(f"📄 Hujjat raqami: {e(a.doc_number)}")
    if a.subject:
        rows.append(f"📌 {e(a.subject)}")
    if a.message:
        rows += ["", e(a.message)]
    rows += ["", f"🕒 {timezone.localtime(a.created_at):%d.%m.%Y %H:%M}"]
    return "\n".join(rows)


ATTEMPTS = 3  # internet bir lahza uzilsa — qayta urinamiz


def _send(text: str) -> None:
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in settings.TELEGRAM_CHAT_IDS:
        body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        for attempt in range(1, ATTEMPTS + 1):
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            try:
                urllib.request.urlopen(req, timeout=15).close()
                break
            except urllib.error.HTTPError as exc:  # Telegram rad etdi (masalan, noto'g'ri chat) — qayta urinish foydasiz
                log.warning("Telegram rad etdi (%s): %s %s", chat_id, exc.code, exc.read()[:200])
                break
            except Exception as exc:  # Telegram ishlamasa ham murojaat bazada saqlangan bo'ladi
                if attempt == ATTEMPTS:
                    log.warning("Telegramga yuborib bo'lmadi (%s): %s", chat_id, exc)
                else:
                    time.sleep(2 * attempt)


def notify_appeal(appeal, suspect: bool = False) -> None:
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_IDS:
        return
    # Fonda — sayt formasi Telegram javobini kutmaydi
    threading.Thread(target=_send, args=(appeal_text(appeal, suspect),), daemon=True).start()
