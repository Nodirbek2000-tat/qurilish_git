"""Arxan Residence: 1 m² narxi 9 500 000 so'm (narx hali kiritilmagan bo'lsa). Serverdagi bazaga ham o'zi tushadi."""

from django.db import migrations


def set_price(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    Project.objects.filter(slug="arxan-residence", price_m2__isnull=True).update(price_m2=9_500_000)


class Migration(migrations.Migration):
    dependencies = [("core", "0017_project_price_m2")]
    operations = [migrations.RunPython(set_price, migrations.RunPython.noop)]
