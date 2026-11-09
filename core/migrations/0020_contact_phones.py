"""Saytdagi aloqa raqamlari (telefon hali kiritilmagan bo'lsa). Serverdagi bazaga ham o'zi tushadi."""

from django.db import migrations

PHONES = "+998 94 504 44 66, +998 99 595 55 66, +998 93 871 40 40"


def set_phones(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    s, _ = SiteSettings.objects.get_or_create(pk=1)
    if not s.phone:
        s.phone = PHONES
        s.save(update_fields=["phone"])


class Migration(migrations.Migration):
    dependencies = [("core", "0019_site_phones")]
    operations = [migrations.RunPython(set_phones, migrations.RunPython.noop)]
