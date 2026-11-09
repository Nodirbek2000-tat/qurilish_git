from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import bot_api, panel_api, views
from core.panel import CodeStepView, PasswordStepView

panel = settings.PANEL_PATH

api = [
    path("site/", views.site),
    path("projects/", views.projects),
    path("projects/<slug:slug>/", views.project_detail),
    path("posts/", views.posts),
    path("posts/<slug:slug>/", views.post_detail),
    path("projects/<slug:slug>/genplan/", views.genplan),
    path("buildings/<int:pk>/", views.building),
    path("flats/", views.flats),
    path("flats/by-ids/", views.flats_by_ids),
    path("flats/<int:pk>/", views.flat_detail),
    path("appeals/", views.create_appeal),
    # Telegram bot (qurilish_bot, X-Bot-Key): panelga kirish va /admin
    path("bot/contact/", bot_api.contact),
    path("bot/me/", bot_api.me),
    path("bot/link/", bot_api.link),
    path("bot/stats/", bot_api.stats),
    path("bot/access/", bot_api.access_list),
    path("bot/access/add/", bot_api.access_add),
    path("bot/access/delete/", bot_api.access_delete),
    # Next.js admin paneli (faqat Next serveri, X-Site-Key + token). Kirish — faqat bot havolasi bilan
    path("panel/telegram-login/", panel_api.telegram_login),
    path("panel/me/", panel_api.me),
    path("panel/dashboard/", panel_api.dashboard),
    path("panel/schema/", panel_api.schema),
    path("panel/appeals/", panel_api.appeals),
    path("panel/appeals/<int:pk>/", panel_api.appeals),
    path("panel/flats/", panel_api.flats_overview),
    path("panel/flat-layout/", panel_api.layout_ensure),
    path("panel/<slug:kind>/", panel_api.crud),
    path("panel/<slug:kind>/<int:pk>/", panel_api.crud),
]

# /admin/ ataylab yo'q — panel faqat uzun maxfiy manzilda
urlpatterns = [
    path("api/", include(api)),
    path(f"{panel}/kirish/", PasswordStepView.as_view(), name="panel_login"),
    path(f"{panel}/kirish/kod/", CodeStepView.as_view(), name="panel_code"),
    path(f"{panel}/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
