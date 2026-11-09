"""Arxan — Django sozlamalari.

Barcha sirlar `.env` dan olinadi (namuna: `.env.example`).
SECRET_KEY va PANEL_PATH bo'lmasa server ishga tushmaydi.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    """Oddiy .env o'quvchi: KEY=VALUE qatorlari, # izoh."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"{name} .env da ko'rsatilmagan")
    return value


def env_list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in env(name, default).split(",") if x.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")  # default yo'q — ataylab
DEBUG = env("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Panel manzili — uzun va taxmin qilib bo'lmaydigan yo'l. /admin/ yo'q.
PANEL_PATH = env("PANEL_PATH").strip("/")
if len(PANEL_PATH) < 24:
    raise ImproperlyConfigured("PANEL_PATH kamida 24 belgi bo'lsin")

# Next.js serveri bilan umumiy kalitlar
SITE_API_KEY = env("SITE_API_KEY")
NEXT_REVALIDATE_URL = env("NEXT_REVALIDATE_URL", "")
NEXT_REVALIDATE_SECRET = env("NEXT_REVALIDATE_SECRET", "")
SITE_URL = env("SITE_URL", "http://localhost:3000")

# Panelga kirishda 2-bosqich (autentifikator kodi) — faqat Django admin uchun. Yoqish: PANEL_TWO_FACTOR=1
PANEL_TWO_FACTOR = env("PANEL_TWO_FACTOR", "0") == "1"

# Next panelga kirish faqat Telegram bot orqali (login/parol yo'q).
# Bot (qurilish_bot) shu kalit bilan /api/bot/ ga murojaat qiladi; bot bergan havola — PANEL_LOGIN_URL?t=...
BOT_API_KEY = env("BOT_API_KEY", "")
PANEL_LOGIN_URL = env("PANEL_LOGIN_URL", f"{SITE_URL}/panel/kirish")
PANEL_LINK_AGE = 5 * 60  # bir martalik havola 5 daqiqa amal qiladi

# Yangi murojaatlar Telegram botga keladi (bo'sh bo'lsa — yuborilmaydi)
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_IDS = env_list("TELEGRAM_CHAT_ID")

INSTALLED_APPS = [
    "unfold.apps.BasicAppConfig",  # o'z admin saytini o'rnatmasin — bizniki 2FA bilan
    "core.apps.PanelAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Serverda (Docker) baza va fayllar /data ichida turadi — konteyner yangilansa ham saqlanadi
DATA_DIR = Path(env("DJANGO_DATA_DIR", str(BASE_DIR)))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        # WAL: o'qish va yozish bir-birini kutmaydi; bir vaqtda yozilsa — 20 s gacha navbat kutadi
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
        },
    }
}

# Fayl keshi — bir nechta worker orasida urinishlar hisobi umumiy bo'ladi
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": env("DJANGO_CACHE_DIR", str(BASE_DIR / ".cache")),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/uploads/"  # /media/ — saytdagi "Media" bo'limi uchun band
MEDIA_ROOT = DATA_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Sessiya: panel 8 soatdan keyin qayta kirishni so'raydi
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env("DJANGO_SSL_REDIRECT", "1") == "1"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"core": {"handlers": ["console"], "level": "INFO"}},
}

# ---- Panel ko'rinishi (Unfold) ----
from django.urls import reverse_lazy  # noqa: E402

UNFOLD = {
    "SITE_TITLE": "Arxan panel",
    "SITE_HEADER": "ARXAN",
    "SITE_SUBHEADER": "Boshqaruv paneli",
    "SITE_URL": SITE_URL,
    "SITE_SYMBOL": "apartment",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "COLORS": {
        "base": {
            "50": "oklch(98.5% .003 80)",
            "100": "oklch(96.5% .005 80)",
            "200": "oklch(92.5% .008 80)",
            "300": "oklch(86.5% .01 80)",
            "400": "oklch(70% .012 80)",
            "500": "oklch(55% .012 80)",
            "600": "oklch(44.5% .012 80)",
            "700": "oklch(37% .01 80)",
            "800": "oklch(27.5% .008 80)",
            "900": "oklch(21% .006 80)",
            "950": "oklch(14% .005 80)",
        },
        "primary": {
            "50": "oklch(97% .015 45)",
            "100": "oklch(94% .03 45)",
            "200": "oklch(88% .06 45)",
            "300": "oklch(80% .1 45)",
            "400": "oklch(70% .13 45)",
            "500": "oklch(62% .14 45)",
            "600": "oklch(55% .13 45)",
            "700": "oklch(47% .11 45)",
            "800": "oklch(40% .09 45)",
            "900": "oklch(34% .07 45)",
            "950": "oklch(24% .05 45)",
        },
    },
    "SIDEBAR": {
        "show_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Sayt",
                "items": [
                    {"title": "Loyihalar", "icon": "apartment", "link": reverse_lazy("admin:core_project_changelist")},
                    {"title": "Bloklar", "icon": "domain", "link": reverse_lazy("admin:core_building_changelist")},
                    {"title": "Xonadonlar", "icon": "door_front", "link": reverse_lazy("admin:core_flat_changelist")},
                    {"title": "Media", "icon": "newspaper", "link": reverse_lazy("admin:core_post_changelist")},
                    {"title": "Murojaatlar", "icon": "mail", "link": reverse_lazy("admin:core_appeal_changelist")},
                ],
            },
            {
                "title": "Kompaniya",
                "items": [
                    {"title": "Sayt sozlamalari", "icon": "tune", "link": reverse_lazy("admin:core_sitesettings_changelist")},
                    {"title": "Sotuv ofislari", "icon": "storefront", "link": reverse_lazy("admin:core_salesoffice_changelist")},
                    {"title": "Tarix", "icon": "history", "link": reverse_lazy("admin:core_milestone_changelist")},
                    {"title": "Faoliyat", "icon": "workspace_premium", "link": reverse_lazy("admin:core_activity_changelist")},
                ],
            },
            {
                "title": "Xavfsizlik",
                "items": [
                    {"title": "Panelga ruxsatlar (bot)", "icon": "verified_user", "link": reverse_lazy("admin:core_panelaccess_changelist")},
                    {"title": "Kirish tarixi", "icon": "login", "link": reverse_lazy("admin:core_panelloginevent_changelist")},
                    {"title": "Foydalanuvchilar", "icon": "person", "link": reverse_lazy("admin:auth_user_changelist")},
                ],
            },
        ],
    },
}
