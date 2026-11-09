"""RFC 6238 TOTP — Google Authenticator / Microsoft Authenticator bilan mos.

Tashqi kutubxonasiz: faqat standart hmac.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def verify(secret: str, code: str, last_step: int = 0, window: int = 1) -> int | None:
    """Kod to'g'ri bo'lsa ishlatilgan qadam raqamini qaytaradi, aks holda None.

    `last_step` dan oldingi yoki teng qadamlar rad etiladi (kodni qayta ishlatish himoyasi).
    """
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    now = int(time.time()) // STEP
    for step in range(now - window, now + window + 1):
        if step > last_step and hmac.compare_digest(_code(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "Arxan") -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"
