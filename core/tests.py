import json
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from . import totp
from .models import Appeal, Project, TwoFactor
from .telegram import appeal_text

PANEL = f"/{settings.PANEL_PATH}/"


def _panel_login(client, name="Boss Bossov", phone="+998901112233", role="admin", telegram_id=111):
    """Bot bergan havola orqali panelga kirish: (sessiya tokeni, PanelAccess)."""
    import secrets
    from datetime import timedelta

    from django.utils import timezone

    from .bot_api import token_hash
    from .models import PanelAccess, PanelLoginLink
    access = PanelAccess.objects.create(full_name=name, phone=phone, role=role, telegram_id=telegram_id)
    raw = secrets.token_urlsafe(16)
    PanelLoginLink.objects.create(access=access, token_hash=token_hash(raw), expires_at=timezone.now() + timedelta(minutes=5))
    r = client.post("/api/panel/telegram-login/", json.dumps({"token": raw}), content_type="application/json",
                    HTTP_X_SITE_KEY=settings.SITE_API_KEY)
    return r.json()["token"], access


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
                   PANEL_TWO_FACTOR=False)
class PanelWithoutTwoFactorTests(TestCase):
    """Hozirgi holat: 2-bosqich o'chiq — login+parol yetarli, lekin bloklash ishlaydi."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_superuser("boss", password="Juda-uzun-parol-123")
        self.key = {"HTTP_X_SITE_KEY": settings.SITE_API_KEY}

    def test_password_logs_in_directly(self):
        r = self.client.post(PANEL + "kirish/", {"username": "boss", "password": "Juda-uzun-parol-123"})
        self.assertRedirects(r, PANEL, fetch_redirect_response=False)
        self.assertEqual(self.client.get(PANEL).status_code, 200)

    def test_wrong_password_still_locks(self):
        for _ in range(5):
            self.client.post(PANEL + "kirish/", {"username": "boss", "password": "xato"})
        r = self.client.post(PANEL + "kirish/", {"username": "boss", "password": "Juda-uzun-parol-123"})
        self.assertEqual(r.status_code, 429)

    def test_password_api_login_is_gone(self):
        r = self.client.post("/api/panel/login/", json.dumps({"username": "boss", "password": "Juda-uzun-parol-123"}),
                             content_type="application/json", **self.key)
        self.assertEqual(r.status_code, 401)  # login/parol bilan kirish yo'li yo'q — token berilmaydi
        self.assertNotIn("token", r.json())

    def test_password_user_session_is_rejected(self):
        # Botda ruxsati yo'q (eski login/parolli) foydalanuvchi tokeni panelga o'tmaydi
        from .panel_api import _session
        token = _session(self.user)["token"]
        self.assertEqual(self.client.get("/api/panel/me/", **self.key, HTTP_AUTHORIZATION=f"Bearer {token}").status_code, 401)

    def test_project_delete_removes_flats_keeps_appeals(self):
        from .models import Building, Flat
        token, _ = _panel_login(self.client)
        auth = {**self.key, "HTTP_AUTHORIZATION": f"Bearer {token}"}
        project = Project.objects.create(title="A", slug="a", description="x", address="y")
        building = Building.objects.create(project=project, number=1, floors=12)
        Flat.objects.create(building=building, number="1", rooms=2, area=50, floor=2)
        appeal = Appeal.objects.create(name="Ali", phone="+998901234567", project=project)
        self.assertEqual(self.client.get(f"/api/panel/project/{project.pk}/", **auth).json()["flatTotal"], 1)
        self.assertEqual(self.client.delete(f"/api/panel/project/{project.pk}/", **auth).status_code, 200)
        self.assertFalse(Project.objects.exists())
        self.assertFalse(Flat.objects.exists())
        appeal.refresh_from_db()
        self.assertIsNone(appeal.project)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
                   PANEL_TWO_FACTOR=True)  # keyin yoqilganda ham ishlashi tekshirib turiladi
class PanelAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_superuser("boss", password="Juda-uzun-parol-123")

    def login_password(self, password="Juda-uzun-parol-123"):
        return self.client.post(PANEL + "kirish/", {"username": "boss", "password": password})

    def test_admin_path_does_not_exist(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_anonymous_redirected_to_login(self):
        r = self.client.get(PANEL, follow=True)
        self.assertEqual(r.redirect_chain[-1][0], PANEL + "kirish/")
        self.assertEqual(r.status_code, 200)

    def test_password_alone_is_not_enough(self):
        self.assertRedirects(self.login_password(), PANEL + "kirish/kod/")
        self.assertEqual(self.client.get(PANEL).status_code, 302)  # hali kodsiz

    def test_wrong_password(self):
        self.assertEqual(self.login_password("xato").status_code, 401)

    def test_django_session_login_without_otp_is_rejected(self):
        self.client.force_login(self.user)  # parol bor, lekin 2FA yo'q
        self.assertEqual(self.client.get(PANEL).status_code, 302)

    def test_full_two_step_login(self):
        self.login_password()
        self.client.get(PANEL + "kirish/kod/")
        device = TwoFactor.objects.get(user=self.user)
        code = totp._code(device.secret, int(__import__("time").time()) // totp.STEP)
        r = self.client.post(PANEL + "kirish/kod/", {"code": code})
        self.assertRedirects(r, PANEL, fetch_redirect_response=False)
        self.assertEqual(self.client.get(PANEL).status_code, 200)
        # shu kodni qayta ishlatib bo'lmaydi
        self.assertIsNone(totp.verify(device.secret, code, TwoFactor.objects.get(pk=device.pk).last_step))

    def test_wrong_code_and_lockout(self):
        self.login_password()
        for _ in range(5):
            self.assertEqual(self.client.post(PANEL + "kirish/kod/", {"code": "000000"}).status_code, 401)
        self.assertEqual(self.login_password().status_code, 429)

    def test_non_staff_cannot_login(self):
        get_user_model().objects.create_user("oddiy", password="Juda-uzun-parol-123")
        r = self.client.post(PANEL + "kirish/", {"username": "oddiy", "password": "Juda-uzun-parol-123"})
        self.assertEqual(r.status_code, 401)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
                   TELEGRAM_BOT_TOKEN="")  # testlar haqiqiy botga yozmasin
class ApiTests(TestCase):
    def setUp(self):
        cache.clear()
        Project.objects.create(title="A", slug="a", description="x", address="y")
        Project.objects.create(title="B", slug="b", description="x", address="y", is_published=False)

    def post_appeal(self, payload, key=None):
        return self.client.post("/api/appeals/", json.dumps(payload), content_type="application/json",
                                HTTP_X_SITE_KEY=key if key is not None else settings.SITE_API_KEY)

    def test_only_published_projects(self):
        items = self.client.get("/api/projects/").json()["items"]
        self.assertEqual([p["slug"] for p in items], ["a"])
        self.assertEqual(self.client.get("/api/projects/b/").status_code, 404)

    def test_appeal_requires_site_key(self):
        self.assertEqual(self.post_appeal({"name": "Ali", "phone": "+998901234567"}, key="xato").status_code, 403)

    def test_appeal_validation_and_create(self):
        self.assertEqual(self.post_appeal({"name": "A", "phone": "123"}).status_code, 422)
        r = self.post_appeal({"kind": "qongiroq", "name": "Ali", "phone": "+998 90 123 45 67", "project": "a"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Appeal.objects.get().project.slug, "a")

    def test_appeal_rate_limit(self):
        payload = {"kind": "qongiroq", "name": "Ali", "phone": "+998901234567"}
        for _ in range(5):
            self.post_appeal(payload)
        self.assertEqual(self.post_appeal(payload).status_code, 429)

    def test_appeal_goes_to_telegram(self):
        with patch("core.views.notify_appeal") as notify:
            self.post_appeal({"name": "A", "phone": "123"})  # xato — yuborilmaydi
            self.post_appeal({"kind": "qongiroq", "name": "Ali", "phone": "+998901234567"})
        notify.assert_called_once_with(Appeal.objects.get(), suspect=False)

    def test_honeypot_appeal_is_kept_and_flagged(self):
        with patch("core.views.notify_appeal") as notify:
            r = self.post_appeal({"kind": "murojaat", "source": "murojaat", "name": "Ali", "phone": "+998901234567",
                                  "message": "Avtoto'ldirish bilan", "suspect": "1"})
        self.assertEqual(r.status_code, 201)
        a = Appeal.objects.get()
        self.assertIn("Bot bo'lishi mumkin", a.note)
        notify.assert_called_once_with(a, suspect=True)
        self.assertIn("⚠️", appeal_text(a, suspect=True))

    def test_company_appeal_requires_every_field(self):
        base = {"kind": "murojaat", "source": "murojaat", "applicant": "kompaniya", "name": "Ali",
                "phone": "+998901234567", "message": "Shartnoma bo'yicha savol"}
        r = self.post_appeal({**base, "inn": "12"})
        self.assertEqual(set(r.json()["errors"]), {"company", "inn", "email", "doc_number", "subject"})
        r = self.post_appeal({**base, "company": "Qurilish MChJ", "inn": "123456789", "doc_number": "A-15",
                              "email": "info@qurilish.uz", "subject": "Shartnoma"})
        self.assertEqual(r.status_code, 201)
        a = Appeal.objects.get()
        self.assertEqual((a.source, a.applicant, a.company, a.inn, a.doc_number),
                         ("murojaat", "kompaniya", "Qurilish MChJ", "123456789", "A-15"))
        self.assertIn("Murojaat · Kompaniya", appeal_text(a))
        self.assertIn("STIR 123456789", appeal_text(a))

    def test_person_appeal_drops_company_fields(self):
        self.post_appeal({"kind": "qongiroq", "source": "aloqa", "name": "Ali", "phone": "+998901234567",
                          "company": "X MChJ", "inn": "123456789"})
        a = Appeal.objects.get()
        self.assertEqual((a.applicant, a.company, a.inn), ("mijoz", "", ""))
        self.assertIn("📂 Aloqa", appeal_text(a))

    def test_project_category(self):
        a = Appeal.objects.create(kind="qongiroq", source="loyiha", name="Ali", phone="+998901234567",
                                  project=Project.objects.get(slug="a"))
        self.assertIn("Loyiha: A", appeal_text(a))

    @override_settings(TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_IDS=["1"])
    def test_telegram_retries_after_network_error(self):
        from urllib.error import URLError
        from core import telegram
        ok = type("Resp", (), {"close": lambda self: None})()
        with patch("core.telegram.urllib.request.urlopen", side_effect=[URLError("timeout"), ok]) as urlopen, \
             patch("core.telegram.time.sleep"):
            telegram._send("salom")
        self.assertEqual(urlopen.call_count, 2)  # birinchisi uzildi, ikkinchisi yetib bordi

    def test_telegram_text_is_escaped(self):
        a = Appeal.objects.create(kind="qongiroq", name="<b>Ali</b>", phone="+998901234567", message="Qo'ng'iroq",
                                  project=Project.objects.get(slug="a"))
        text = appeal_text(a)
        self.assertIn("Yangi murojaat", text)
        self.assertIn("&lt;b&gt;Ali&lt;/b&gt;", text)
        self.assertIn("Qo'ng'iroq", text)
        self.assertIn("+998901234567", text)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class FlatApiTests(TestCase):
    def setUp(self):
        from .models import Building, Flat
        cache.clear()
        p = Project.objects.create(title="A", slug="a", description="x", address="y")
        b = Building.objects.create(project=p, number=1, floors=5, completion_year=2027)
        self.hidden = Flat.objects.create(building=b, number="1", rooms=2, area=60, floor=2, price=900, show_price=False)
        self.shown = Flat.objects.create(building=b, number="2", rooms=4, area=110, floor=3, price=1500, show_price=True)
        Flat.objects.create(building=b, number="3", rooms=1, area=40, floor=4, status="sotilgan")

    def test_hidden_price_never_leaves_server(self):
        items = {f["number"]: f for f in self.client.get("/api/flats/").json()["items"]}
        self.assertIsNone(items["1"]["price"])
        self.assertEqual(items["2"]["price"], 1500)
        self.assertNotIn("900", self.client.get(f"/api/flats/{self.hidden.pk}/").content.decode())

    def test_filters_and_sold_excluded(self):
        data = self.client.get("/api/flats/?rooms=4").json()
        self.assertEqual([f["number"] for f in data["items"]], ["2"])
        self.assertEqual(self.client.get("/api/flats/").json()["total"], 2)  # sotilgani yo'q


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="arxan-test-"))
class CatalogTests(TestCase):
    def setUp(self):
        from .models import CatalogPage
        self.CatalogPage = CatalogPage
        self.project = Project.objects.create(title="A", slug="a", description="x", address="y")

    def test_pages_are_numbered_automatically_and_served_in_order(self):
        first = self.CatalogPage.objects.create(project=self.project, image=_png(800, 566))
        second = self.CatalogPage.objects.create(project=self.project, image=_png(800, 566))
        inserted = self.CatalogPage.objects.create(project=self.project, image=_png(800, 566), order=1)
        self.assertEqual((first.order, second.order), (1, 2))
        catalog = self.client.get("/api/projects/a/").json()["catalog"]
        self.assertEqual(len(catalog), 3)
        self.assertEqual(catalog[0]["w"], 800)
        self.assertEqual(catalog[0]["h"], 566)
        self.assertEqual(catalog[-1]["src"], second.image.url)  # 2-sahifa oxirida
        self.assertNotEqual(inserted.pk, None)

    def test_other_project_pages_do_not_leak(self):
        other = Project.objects.create(title="B", slug="b", description="x", address="y")
        self.CatalogPage.objects.create(project=other, image=_png(400, 300))
        self.assertEqual(self.CatalogPage.objects.create(project=self.project, image=_png(400, 300)).order, 1)
        self.assertEqual(len(self.client.get("/api/projects/a/").json()["catalog"]), 1)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="arxan-test-"))
class AboutApiTests(TestCase):
    def test_history_and_activities_newest_first(self):
        from .models import Activity, Milestone
        Milestone.objects.create(year=2024, title="Birinchi loyiha")
        Milestone.objects.create(year=2026, title="Charog'bon", image=_png(400, 250))
        Activity.objects.create(year=2025, organization="Assotsiatsiya", title="Yil brendi")
        data = self.client.get("/api/site/").json()
        self.assertEqual([m["year"] for m in data["milestones"]], [2026, 2024])
        self.assertTrue(data["milestones"][0]["image"])
        self.assertIsNone(data["milestones"][1]["image"])
        self.assertEqual(data["activities"], [{"year": 2025, "organization": "Assotsiatsiya", "title": "Yil brendi", "image": None}])


def _png(w, h):
    import io
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "#999").save(buf, "PNG")
    return SimpleUploadedFile(f"t{w}x{h}.png", buf.getvalue(), content_type="image/png")


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class PanelApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.key = {"HTTP_X_SITE_KEY": settings.SITE_API_KEY}
        self.project = Project.objects.create(title="A", slug="a", description="x", address="y")

    def post(self, url, data, **extra):
        return self.client.post(url, json.dumps(data), content_type="application/json", **{**self.key, **extra})

    def token(self):
        return _panel_login(self.client)[0]

    def auth(self, token):
        return {**self.key, "HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_requires_site_key(self):
        r = self.client.post("/api/panel/telegram-login/", json.dumps({"token": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_token_flow_and_invalidation(self):
        self.assertEqual(self.client.get("/api/panel/me/", **self.key).status_code, 401)
        token, access = _panel_login(self.client)
        self.assertEqual(self.client.get("/api/panel/me/", **self.auth(token)).status_code, 200)
        self.assertEqual(self.client.get("/api/panel/me/", **self.auth(token + "x")).status_code, 401)
        access.delete()  # botda ruxsat olib tashlandi — ochiq sessiya ham darhol yopiladi
        self.assertEqual(self.client.get("/api/panel/me/", **self.auth(token)).status_code, 401)

    def test_image_size_is_enforced(self):
        h = self.auth(self.token())
        bad = self.client.post("/api/panel/project/%d/" % self.project.pk, {"hero": _png(800, 600)}, **h)
        self.assertEqual(bad.status_code, 422)
        self.assertIn("1920", bad.json()["errors"]["hero"][0])
        ok = self.client.post("/api/panel/project/%d/" % self.project.pk, {"hero": _png(1920, 1080)}, **h)
        self.assertEqual(ok.status_code, 200, ok.content)
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, "A")  # qisman yangilash — boshqa maydonlar saqlandi
        self.assertTrue(self.project.hero)

    def test_about_image_xor_video(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        h = self.auth(self.token())
        r = self.client.post("/api/panel/project/%d/" % self.project.pk, {
            "about_image": _png(1200, 900),
            "about_video": SimpleUploadedFile("v.mp4", b"0" * 100, content_type="video/mp4")}, **h)
        self.assertEqual(r.status_code, 422)

    def test_old_image_does_not_block_other_edits(self):
        from django.core.files.base import ContentFile
        import io
        from PIL import Image
        buf = io.BytesIO(); Image.new("RGB", (500, 300)).save(buf, "PNG")
        self.project.hero.save("eski.png", ContentFile(buf.getvalue()))  # yangi qoidaga mos emas
        h = self.auth(self.token())
        r = self.client.post("/api/panel/project/%d/" % self.project.pk, {"tagline": "Yangi shior"}, **h)
        self.assertEqual(r.status_code, 200, r.content)
        self.project.refresh_from_db()
        self.assertEqual(self.project.tagline, "Yangi shior")

    def test_switch_about_image_to_video(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        h = self.auth(self.token())
        url = "/api/panel/project/%d/" % self.project.pk
        self.assertEqual(self.client.post(url, {"about_image": _png(1200, 900)}, **h).status_code, 200)
        r = self.client.post(url, {"clear_about_image": "1",
                                   "about_video": SimpleUploadedFile("v.mp4", b"0" * 100, content_type="video/mp4")}, **h)
        self.assertEqual(r.status_code, 200, r.content)
        self.project.refresh_from_db()
        self.assertFalse(self.project.about_image)
        self.assertTrue(self.project.about_video)

    def test_child_crud(self):
        h = self.auth(self.token())
        r = self.client.post("/api/panel/lobby/", {"project": self.project.pk, "icon": "cctv", "label": "Kamera"}, **h)
        self.assertEqual(r.status_code, 201, r.content)
        items = self.client.get(f"/api/panel/lobby/?project={self.project.pk}", **h).json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(self.client.delete(f"/api/panel/lobby/{items[0]['id']}/", **h).status_code, 200)


class PanelSchemaTests(TestCase):
    def test_image_fields_are_images_with_size(self):
        from .panel_api import _field_schema
        hero = _field_schema(Project, "hero")
        self.assertEqual(hero["type"], "image")
        self.assertEqual(hero["size"], {"minW": 1920, "minH": 1080, "ratio": [16, 9]})
        self.assertEqual(_field_schema(Project, "about_video")["type"], "file")


@override_settings(BOT_API_KEY="bot-test-kaliti", PANEL_LOGIN_URL="http://sayt.test/panel/kirish")
class TelegramBotLoginTests(TestCase):
    """Panelga kirish: /start → raqam → bir martalik havola. /admin — faqat adminlar."""

    def setUp(self):
        from .models import PanelAccess
        self.PanelAccess = PanelAccess
        self.boss = PanelAccess.objects.create(full_name="Boss Bossov", phone="+998901112233", role="admin")

    def bot(self, url, data, key="bot-test-kaliti"):
        return self.client.post(f"/api/bot/{url}/", json.dumps(data), content_type="application/json", HTTP_X_BOT_KEY=key)

    def link_token(self, tid):
        return self.bot("link", {"telegram_id": tid}).json()["url"].split("?t=")[1]

    def login(self, token):
        return self.client.post("/api/panel/telegram-login/", json.dumps({"token": token}), content_type="application/json",
                                HTTP_X_SITE_KEY=settings.SITE_API_KEY, HTTP_X_CLIENT_IP="1.2.3.4")

    def test_requires_bot_key(self):
        self.assertEqual(self.bot("me", {"telegram_id": 1}, key="xato").status_code, 403)
        with override_settings(BOT_API_KEY=""):  # kalit sozlanmagan bo'lsa — hech kim kira olmaydi
            self.assertEqual(self.bot("me", {"telegram_id": 1}, key="").status_code, 403)

    def test_unknown_phone_is_denied(self):
        r = self.bot("contact", {"telegram_id": 555, "phone": "998 90 000 00 00", "name": "Begona"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.bot("link", {"telegram_id": 555}).status_code, 403)

    def test_contact_then_single_use_link(self):
        # Telegram raqamni "998901112233" ko'rinishida yuboradi — bazadagi "+998901112233" bilan mos keladi
        r = self.bot("contact", {"telegram_id": 777, "phone": "998901112233", "name": "Boss"})
        self.assertEqual(r.json(), {"name": "Boss Bossov", "role": "admin"})
        token = self.link_token(777)
        session = self.login(token)
        self.assertEqual(session.status_code, 200)
        me = self.client.get("/api/panel/me/", HTTP_X_SITE_KEY=settings.SITE_API_KEY,
                             HTTP_AUTHORIZATION=f"Bearer {session.json()['token']}")
        self.assertEqual(me.json()["name"], "Boss Bossov")
        self.assertEqual(self.login(token).status_code, 401)  # ikkinchi marta ishlamaydi
        self.boss.refresh_from_db()
        self.assertIsNotNone(self.boss.last_login_at)

    def test_link_expires_and_new_link_cancels_old(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import PanelLoginLink
        self.bot("contact", {"telegram_id": 777, "phone": "+998901112233"})
        old = self.link_token(777)
        new = self.link_token(777)
        self.assertEqual(self.login(old).status_code, 401)
        PanelLoginLink.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.login(new).status_code, 401)

    def test_admin_commands_only_for_admins(self):
        self.bot("contact", {"telegram_id": 777, "phone": "+998901112233"})
        r = self.bot("access/add", {"actor": 777, "name": "Xodim Xodimov", "phone": "90 123 45 67", "role": "xodim"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["phone"], "+998901234567")
        self.assertEqual(self.bot("access/add", {"actor": 777, "name": "Yana Biri", "phone": "+998901234567", "role": "xodim"}).status_code, 400)
        # Xodim /admin buyruqlaridan foydalana olmaydi, lekin panelga kira oladi
        self.bot("contact", {"telegram_id": 888, "phone": "+998901234567"})
        self.assertEqual(self.bot("stats", {"actor": 888}).status_code, 403)
        self.assertEqual(self.bot("access/add", {"actor": 888, "name": "Hacker", "phone": "+998909999999", "role": "admin"}).status_code, 403)
        self.assertEqual(self.login(self.link_token(888)).status_code, 200)
        # Begona Telegram ID — umuman admin emas
        self.assertEqual(self.bot("stats", {"actor": 999}).status_code, 403)

    def test_stats_counts_requests_and_logins(self):
        self.bot("contact", {"telegram_id": 777, "phone": "+998901112233"})
        self.bot("contact", {"telegram_id": 555, "phone": "+998900000000"})  # ruxsatsiz
        self.login(self.link_token(777))
        s = self.bot("stats", {"actor": 777}).json()
        self.assertEqual((s["requests"], s["requestPeople"], s["deniedPeople"]), (2, 2, 1))
        self.assertEqual((s["logins"], s["loginPeople"], s["admins"], s["staff"]), (1, 1, 1, 0))
        self.assertEqual(s["recent"][0]["name"], "Boss Bossov")
        self.assertEqual(s["recent"][0]["ip"], "1.2.3.4")

    def test_delete_access_but_not_self(self):
        self.bot("contact", {"telegram_id": 777, "phone": "+998901112233"})
        self.assertEqual(self.bot("access/delete", {"actor": 777, "id": self.boss.pk}).status_code, 400)
        staff = self.PanelAccess.objects.create(full_name="Xodim Xodimov", phone="+998901234567", role="xodim", telegram_id=888)
        token = self.login(self.link_token(888)).json()["token"]
        self.assertEqual(self.bot("access/delete", {"actor": 777, "id": staff.pk}).status_code, 200)
        me = self.client.get("/api/panel/me/", HTTP_X_SITE_KEY=settings.SITE_API_KEY, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(me.status_code, 401)  # o'chirilgan xodimning ochiq sessiyasi ham yopildi
        # Qayta qo'shsa — yana kira oladi
        again = self.bot("access/add", {"actor": 777, "name": "Xodim Xodimov", "phone": "+998901234567", "role": "xodim"})
        self.assertEqual(again.status_code, 201)
        self.bot("contact", {"telegram_id": 888, "phone": "+998901234567"})
        self.assertEqual(self.login(self.link_token(888)).status_code, 200)

    def test_bootstrap_command(self):
        from django.core.management import call_command
        call_command("bot_admin", "Birinchi Admin", "90-555-44-33", stdout=__import__("io").StringIO())
        a = self.PanelAccess.objects.get(phone="+998905554433")
        self.assertEqual((a.full_name, a.role), ("Birinchi Admin", "admin"))
        self.assertFalse(a.user.has_usable_password())  # parol bilan kirib bo'lmaydi


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="arxan-test-"))
class FlatLayoutTests(TestCase):
    """Xonadon turi: rasmlar bir marta yuklanadi va shu o'lchamdagi hamma xonadonda chiqadi."""

    def setUp(self):
        from .models import Building, Flat
        self.project = Project.objects.create(title="A", slug="a", description="x", address="y")
        b = Building.objects.create(project=self.project, number=1, floors=12)
        self.f1 = Flat.objects.create(building=b, number="1", rooms=2, area="53.58", floor=2)
        self.f2 = Flat.objects.create(building=b, number="2", rooms=2, area="53.58", floor=3, status="sotilgan")
        self.f3 = Flat.objects.create(building=b, number="3", rooms=3, area="81.08", floor=2)
        self.token, _ = _panel_login(self.client)
        self.h = {"HTTP_X_SITE_KEY": settings.SITE_API_KEY, "HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_overview_groups_flats_by_size(self):
        d = self.client.get(f"/api/panel/flats/?project={self.project.pk}", **self.h).json()
        self.assertEqual([(t["rooms"], t["areaRaw"], t["total"], t["available"]) for t in d["types"]],
                         [(2, "53.58", 2, 1), (3, "81.08", 1, 1)])
        self.assertEqual(len(d["flats"]), 3)

    def test_layout_images_show_on_every_flat_of_that_size(self):
        r = self.client.post("/api/panel/flat-layout/", json.dumps({"project": self.project.pk, "rooms": 2, "area": "53.58"}),
                             content_type="application/json", **self.h)
        lid = r.json()["id"]
        # Ikkinchi marta — o'sha yozuv (dublikat yaratilmaydi)
        again = self.client.post("/api/panel/flat-layout/", json.dumps({"project": self.project.pk, "rooms": 2, "area": "53.58"}),
                                 content_type="application/json", **self.h)
        self.assertEqual(again.json()["id"], lid)
        up = self.client.post("/api/panel/layoutimage/", {"layout": lid, "image": _png(1200, 800), "caption": "Mehmonxona"}, **self.h)
        self.assertEqual(up.status_code, 201, up.content)
        self.client.post(f"/api/panel/layout/{lid}/", {"description": "Yorug' xonadon.\n\nKatta oshxona."}, **self.h)
        d = self.client.get(f"/api/flats/{self.f1.pk}/").json()
        self.assertEqual([g["caption"] for g in d["gallery"]], ["Mehmonxona"])
        self.assertEqual(d["about"], ["Yorug' xonadon.", "Katta oshxona."])
        self.assertEqual(self.client.get(f"/api/flats/{self.f3.pk}/").json()["gallery"], [])  # boshqa o'lcham

    def test_room_parts_saved_validated_and_kept(self):
        lid = self.client.post("/api/panel/flat-layout/", json.dumps({"project": self.project.pk, "rooms": 2, "area": "53.58"}),
                               content_type="application/json", **self.h).json()["id"]
        parts = [{"name": "Dahliz", "area": "11,51"}, {"name": " Oshxona ", "area": 8.47}, {"name": "", "area": ""}]
        r = self.client.post(f"/api/panel/layout/{lid}/", {"parts": json.dumps(parts)}, **self.h)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["parts"], [{"name": "Dahliz", "area": 11.51}, {"name": "Oshxona", "area": 8.47}])
        bad = self.client.post(f"/api/panel/layout/{lid}/", {"parts": json.dumps([{"name": "Xona", "area": "katta"}])}, **self.h)
        self.assertEqual(bad.status_code, 422)
        # Faqat tavsif saqlansa — xonalar o'chib ketmaydi
        self.client.post(f"/api/panel/layout/{lid}/", {"description": "Yorug'"}, **self.h)
        self.assertEqual(len(self.client.get(f"/api/flats/{self.f1.pk}/").json()["parts"]), 2)

    def test_add_flat_and_quick_status_change(self):
        b = self.f1.building
        r = self.client.post("/api/panel/flat/", {"building": b.pk, "number": "99", "floor": 5, "kind": "turar", "rooms": 1,
                                                  "area": "40.5", "status": "sotuvda"}, **self.h)
        self.assertEqual(r.status_code, 201, r.content)
        r = self.client.post(f"/api/panel/flat/{r.json()['id']}/", {"status": "band"}, **self.h)
        self.assertEqual(r.json()["status"], "band")


class AppealFilterTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone
        self.token, _ = _panel_login(self.client)
        self.h = {"HTTP_X_SITE_KEY": settings.SITE_API_KEY, "HTTP_AUTHORIZATION": f"Bearer {self.token}"}
        Appeal.objects.create(name="Bugungi Ali", phone="+998 90 123 45 67", source="xonadon")
        old = Appeal.objects.create(name="Eski Vali", phone="+998 91 000 00 00", source="aloqa", state="hal_qilindi")
        Appeal.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=10))

    def get(self, qs=""):
        return self.client.get(f"/api/panel/appeals/{qs}", **self.h).json()

    def test_filters(self):
        self.assertEqual([a["name"] for a in self.get("?davr=bugun")["items"]], ["Bugungi Ali"])
        self.assertEqual([a["name"] for a in self.get("?davr=oy&manba=aloqa")["items"]], ["Eski Vali"])
        self.assertEqual([a["name"] for a in self.get("?q=901234567")["items"]], ["Bugungi Ali"])  # bo'sh joysiz qidiruv
        self.assertEqual([a["name"] for a in self.get("?q=vali")["items"]], ["Eski Vali"])
        d = self.get("?state=yangi")
        self.assertEqual(d["total"], 1)
        self.assertEqual({s["value"]: s["count"] for s in d["states"]}, {"yangi": 1, "korildi": 0, "hal_qilindi": 1})


class UysotTests(TestCase):
    """Arizalar Uysot CRM'ga: token bo'lsa yuboriladi, bo'lmasa — yo'q. Haqiqiy Uysot'ga so'rov ketmaydi (urlopen soxta)."""

    def setUp(self):
        cache.clear()
        Project.objects.create(title="Arxan Residence", slug="arxan-residence", description="d", address="x")

    def post_appeal(self, payload):
        return self.client.post("/api/appeals/", data=json.dumps(payload), content_type="application/json",
                                HTTP_X_SITE_KEY=settings.SITE_API_KEY)

    def run_sync(self, payload):
        """Fon oqimini kutmaslik uchun — send_lead ichidagi Thread'ni darhol bajaramiz."""
        sent = []

        class FakeResp:
            def close(self):
                pass

        def fake_urlopen(req, timeout=None):
            sent.append(req)
            return FakeResp()

        class SyncThread:
            def __init__(self, target, args, daemon=None):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with patch("core.views.notify_appeal"), patch("core.uysot.threading.Thread", SyncThread), \
             patch("core.uysot.urllib.request.urlopen", fake_urlopen):
            r = self.post_appeal(payload)
        return r, sent

    @override_settings(UYSOT_TOKEN="", UYSOT_URL="http://127.0.0.1:9/yoq")
    def test_without_token_nothing_is_sent(self):
        r, sent = self.run_sync({"kind": "qongiroq", "source": "ariza", "name": "Ali", "phone": "+998901234567"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(sent, [])

    @override_settings(UYSOT_TOKEN="sinov-token", UYSOT_URL="http://127.0.0.1:9/v1/external-source")
    def test_lead_format_matches_uysot_docs(self):
        r, sent = self.run_sync({"kind": "qongiroq", "source": "ariza", "name": "Ali Valiyev",
                                 "phone": "+998 90 123 45 67", "project": "arxan-residence"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(sent), 1)
        req = sent[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "http://127.0.0.1:9/v1/external-source")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(req.get_header("X-auth"), "sinov-token")
        body = json.loads(req.data)
        self.assertEqual(body["phoneNumber"], "+998901234567")
        self.assertEqual(body["name"], "Ali Valiyev")
        self.assertEqual(body["tagList"], ["#website", "#arxan.uz"])
        self.assertEqual(body["houseName"], "Arxan Residence")
        self.assertEqual(body["esType"], "WEBSITE")
        self.assertIn("Saytdan:", body["message"])

    @override_settings(UYSOT_TOKEN="sinov-token", UYSOT_URL="http://127.0.0.1:9/v1/external-source")
    def test_bot_filled_form_is_not_sent(self):
        r, sent = self.run_sync({"kind": "qongiroq", "name": "Ali", "phone": "+998901234567", "suspect": "1"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(sent, [])

    @override_settings(UYSOT_TOKEN="sinov-token", UYSOT_URL="http://127.0.0.1:9/v1/external-source")
    def test_invalid_appeal_is_not_sent(self):
        r, sent = self.run_sync({"kind": "qongiroq", "name": "A", "phone": "123"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(sent, [])
