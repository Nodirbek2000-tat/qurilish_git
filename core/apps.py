from django.apps import AppConfig
from django.contrib.admin import apps as admin_apps


class CoreConfig(AppConfig):
    default = True
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Sayt"

    def ready(self):
        from . import signals  # noqa: F401


class PanelAdminConfig(admin_apps.AdminConfig):
    default = False
    """Standart admin o'rniga 2 bosqichli tekshiruvli panel."""

    default_site = "core.panel.PanelSite"
