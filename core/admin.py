from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from django.utils.safestring import mark_safe

from .models import (Activity, Appeal, ArchItem, Building, CatalogPage, InfraPoint, InteriorSlide, LobbyFeature, Flat, FloorPlan, Milestone, Post, PostImage, Project, ProjectImage,
                     PanelAccess, PanelLoginEvent, SalesOffice, SiteSettings, TwoFactor)


def thumb(field, size=56):
    if not field:
        return "—"
    return format_html('<img src="{}" style="width:{}px;height:{}px;object-fit:cover;border-radius:8px">',
                       field.url, size, size)


class ProjectImageInline(TabularInline):
    model = ProjectImage
    extra = 1
    fields = ("image", "caption", "order")


class CatalogPageInline(TabularInline):
    """Saytda kitobdek varaqlanadigan katalog. Raqam 0 qolsa — keyingisi o'zi beriladi."""
    model = CatalogPage
    extra = 1
    fields = ("preview", "image", "order")
    readonly_fields = ("preview",)

    @admin.display(description="")
    def preview(self, obj):
        return thumb(obj.image)


class ArchInline(TabularInline):
    model = ArchItem
    extra = 0
    fields = ("title", "text", "image", "order")


class InteriorInline(TabularInline):
    model = InteriorSlide
    extra = 0
    fields = ("title", "text", "image", "order")


class LobbyFeatureInline(TabularInline):
    model = LobbyFeature
    extra = 0
    fields = ("icon", "label", "order")


class InfraInline(TabularInline):
    model = InfraPoint
    extra = 0
    fields = ("category", "name", "latitude", "longitude")


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ("preview", "title", "status", "klass", "is_published", "order")
    list_display_links = ("preview", "title")
    list_editable = ("is_published", "order")
    list_filter = ("status", "klass", "is_published")
    search_fields = ("title", "address")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ArchInline, InteriorInline, LobbyFeatureInline, InfraInline, ProjectImageInline, CatalogPageInline]
    fieldsets = (
        ("Asosiy", {"fields": ("title", "slug", "status", "klass", "tagline", "color")}),
        ("Rasmlar", {"fields": ("hero", "cover", "logo", "genplan")}),
        ("Loyiha haqida", {"fields": ("description", "about_image", "about_video", ("stat_blocks", "stat_queues"), "features")}),
        ("Lobbi", {"fields": ("lobby_title", "lobby_text", "lobby_image")}),
        ("Onlayn", {"fields": ("live_url", "tour_url")}),
        ("Raqamlar", {"fields": (("floors", "flats", "area"), "handover")}),
        ("Manzil va xarita", {"fields": ("address", ("latitude", "longitude"), "office"),
                              "description": "Koordinatani Yandex xaritada nuqtani bosib olish mumkin"}),
        ("Ko'rinish", {"fields": ("is_published", "order")}),
    )

    @admin.display(description="")
    def preview(self, obj):
        return thumb(obj.cover)


class FloorPlanInline(TabularInline):
    model = FloorPlan
    extra = 0
    fields = ("floor", "image")


class FlatInline(TabularInline):
    model = Flat
    extra = 0
    fields = ("number", "kind", "floor", "rooms", "area", "price", "show_price", "status", "plan")
    show_change_link = True


@admin.register(Building)
class BuildingAdmin(ModelAdmin):
    list_display = ("__str__", "floors", "queue", "completion_year", "available_flats")
    list_filter = ("project", "queue", "completion_year")
    readonly_fields = ("placement",)
    fieldsets = (
        (None, {"fields": ("project", ("number", "floors"), ("queue", "completion_year"))}),
        ("Genplandagi joyi", {"fields": ("placement", ("plan_x", "plan_y")),
                              "description": "Rasm ustida blok turgan joyni bosing — X va Y o'zi to'ladi"}),
    )
    inlines = [FloorPlanInline, FlatInline]

    @admin.display(description="Sotuvda")
    def available_flats(self, obj):
        return obj.flats.filter(status=Flat.Status.AVAILABLE).count()

    @admin.display(description="Genplan")
    def placement(self, obj):
        project = obj.project if obj and obj.pk else None
        if not project or not project.genplan:
            return "Avval loyihaga genplan rasmini yuklang va blokni saqlang."
        # Rasmni bosganda id_plan_x / id_plan_y maydonlari to'ladi
        return mark_safe(f"""
<div id="gp" style="position:relative;max-width:720px;cursor:crosshair;border-radius:12px;overflow:hidden">
  <img src="{project.genplan.url}" style="width:100%;display:block">
  <span id="gp-dot" style="position:absolute;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;
    background:{project.color};border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.4);
    left:{obj.plan_x}%;top:{obj.plan_y}%"></span>
</div>
<script>
document.getElementById('gp').addEventListener('click', function (e) {{
  var r = this.getBoundingClientRect();
  var x = ((e.clientX - r.left) / r.width * 100).toFixed(2), y = ((e.clientY - r.top) / r.height * 100).toFixed(2);
  document.getElementById('id_plan_x').value = x; document.getElementById('id_plan_y').value = y;
  var d = document.getElementById('gp-dot'); d.style.left = x + '%'; d.style.top = y + '%';
}});
</script>""")


@admin.register(Flat)
class FlatAdmin(ModelAdmin):
    list_display = ("number", "building", "floor", "rooms", "area", "price", "show_price", "status")
    list_editable = ("price", "show_price", "status")
    list_filter = ("status", "rooms", "kind", "building__project", "building")
    search_fields = ("number",)
    list_per_page = 50


@admin.register(SalesOffice)
class SalesOfficeAdmin(ModelAdmin):
    list_display = ("name", "address", "phone", "order")
    list_editable = ("order",)


class PostImageInline(TabularInline):
    model = PostImage
    extra = 1
    fields = ("image", "order")


@admin.register(Post)
class PostAdmin(ModelAdmin):
    list_display = ("preview", "title", "kind", "project", "published_at", "is_published")
    list_display_links = ("preview", "title")
    list_editable = ("is_published",)
    list_filter = ("kind", "is_published", "project")
    search_fields = ("title", "excerpt", "body")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"
    inlines = [PostImageInline]
    fieldsets = (
        (None, {"fields": ("title", "slug", "kind", "project", "published_at", "is_published")}),
        ("Kontent", {"fields": ("cover", "excerpt", "body", "video_url")}),
    )

    @admin.display(description="")
    def preview(self, obj):
        return thumb(obj.cover)


@admin.register(Appeal)
class AppealAdmin(ModelAdmin):
    list_display = ("created_at", "name", "phone", "source", "applicant", "kind", "project", "flat", "subject", "state")
    list_filter = ("state", "source", "applicant", "kind", "project", "created_at")
    list_editable = ("state",)
    search_fields = ("name", "phone", "email", "company", "inn", "doc_number", "subject", "message")
    readonly_fields = ("source", "kind", "applicant", "company", "inn", "name", "phone", "email", "country", "doc_number",
                       "subject", "message", "project", "flat", "created_at")
    fields = readonly_fields + ("state", "note")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin):
    fieldsets = (
        ("Aloqa", {"fields": ("phone", "email", "address", ("latitude", "longitude"), "work_hours")}),
        ("Ijtimoiy tarmoqlar", {"fields": ("telegram", "instagram", "facebook", "youtube")}),
        ("Biz haqimizda", {"fields": ("about_title", "about_text")}),
        ("Raqamlar", {"fields": (("founded_year", "stat_projects"), ("stat_families", "stat_area"))}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Milestone)
class MilestoneAdmin(ModelAdmin):
    list_display = ("preview", "year", "title")
    list_display_links = ("preview", "year", "title")
    search_fields = ("title",)

    @admin.display(description="")
    def preview(self, obj):
        return thumb(obj.image)


@admin.register(Activity)
class ActivityAdmin(ModelAdmin):
    list_display = ("preview", "year", "title", "organization")
    list_display_links = ("preview", "year", "title")
    list_filter = ("year",)
    search_fields = ("title", "organization")

    @admin.display(description="")
    def preview(self, obj):
        return thumb(obj.image)


# ---- Panelga Telegram bot orqali kirish ----
@admin.register(PanelAccess)
class PanelAccessAdmin(ModelAdmin):
    list_display = ("full_name", "phone", "role", "linked", "last_login_at", "created_at")
    list_filter = ("role",)
    search_fields = ("full_name", "phone")
    readonly_fields = ("telegram_id", "last_login_at", "added_by", "created_at")

    @admin.display(description="Botga bog'langan", boolean=True)
    def linked(self, obj):
        return obj.telegram_id is not None


@admin.register(PanelLoginEvent)
class PanelLoginEventAdmin(ModelAdmin):
    list_display = ("created_at", "kind", "access", "phone", "name", "ip")
    list_filter = ("kind",)
    search_fields = ("phone", "name", "access__full_name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---- Foydalanuvchilar: Unfold ko'rinishida ----
admin.site.unregister(User)
admin.site.unregister(Group)


class TwoFactorInline(admin.StackedInline):
    model = TwoFactor
    can_delete = True
    fields = ("confirmed",)
    readonly_fields = ("confirmed",)
    verbose_name = "2 bosqichli tekshiruv"
    extra = 0
    max_num = 0  # faqat o'chirish mumkin: o'chirilsa, keyingi kirishda yangi QR chiqadi


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    inlines = [TwoFactorInline]


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
