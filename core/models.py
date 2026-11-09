from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.db import models
from django.utils import timezone
from django.utils.deconstruct import deconstructible

IMAGE_EXT = FileExtensionValidator(["jpg", "jpeg", "png", "webp"])
VIDEO_EXT = FileExtensionValidator(["mp4", "webm"])
HEX_COLOR = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Rang #RRGGBB ko'rinishida bo'lsin, masalan #B85C38")


def max_8mb(file):
    if file.size > 8 * 1024 * 1024:
        raise ValidationError("Rasm hajmi 8 MB dan oshmasin")


def max_40mb(file):
    if file.size > 40 * 1024 * 1024:
        raise ValidationError("Video hajmi 40 MB dan oshmasin")


@deconstructible
class ImageSize:
    """Rasm kamida min_w×min_h bo'lsin va nisbati (masalan 16:9) ±2% dan chetga chiqmasin."""

    def __init__(self, min_w: int, min_h: int, ratio: tuple[int, int] | None = None):
        self.min_w, self.min_h, self.ratio = min_w, min_h, ratio

    def __call__(self, file):
        if getattr(file, "_committed", False):
            return  # allaqachon saqlangan fayl — faqat yangi yuklanganlar tekshiriladi
        w, h = get_image_dimensions(file)
        if not w or not h:
            raise ValidationError("Rasmni o'qib bo'lmadi")
        need = f"{self.min_w}×{self.min_h} px" + (f" ({self.ratio[0]}:{self.ratio[1]})" if self.ratio else "")
        if w < self.min_w or h < self.min_h:
            raise ValidationError(f"Rasm juda kichik: {w}×{h}. Kerak: kamida {need}")
        if self.ratio and abs(w / h - self.ratio[0] / self.ratio[1]) > 0.02 * self.ratio[0] / self.ratio[1]:
            raise ValidationError(f"Nisbat noto'g'ri: {w}×{h}. Kerak: {need}")

    def __eq__(self, other):
        return isinstance(other, ImageSize) and (self.min_w, self.min_h, self.ratio) == (other.min_w, other.min_h, other.ratio)

    @property
    def hint(self) -> str:
        r = f", nisbat {self.ratio[0]}:{self.ratio[1]}" if self.ratio else ""
        return f"Kamida {self.min_w}×{self.min_h} px{r}, JPG/PNG/WebP, 8 MB gacha"


# Har bir joy uchun aniq o'lcham — panelda ham shu matn ko'rsatiladi
SIZE_HERO = ImageSize(1920, 1080, (16, 9))
SIZE_COVER = ImageSize(1200, 900, (4, 3))
SIZE_ABOUT = ImageSize(1200, 900, (4, 3))
SIZE_ARCH = ImageSize(1000, 1250, (4, 5))
SIZE_INTERIOR = ImageSize(1600, 1000, (16, 10))
SIZE_LOBBY = ImageSize(1000, 1250, (4, 5))
SIZE_LOGO = ImageSize(256, 256, (1, 1))
SIZE_OFFICE = ImageSize(400, 400, (1, 1))


def image_field(upload_to, size: ImageSize | None = None, **kw):
    validators = [IMAGE_EXT, max_8mb] + ([size] if size else [])
    if size and "help_text" not in kw:
        kw["help_text"] = size.hint
    return models.ImageField(upload_to=upload_to, validators=validators, **kw)


class Project(models.Model):
    class Status(models.TextChoices):
        BUILDING = "qurilmoqda", "Qurilmoqda"
        SALE = "sotuvda", "Sotuvda"
        DONE = "topshirilgan", "Topshirilgan"

    class Klass(models.TextChoices):
        COMFORT = "komfort", "Komfort"
        BUSINESS = "biznes", "Biznes"
        PREMIUM = "premium", "Premium"

    title = models.CharField("Nomi", max_length=120)
    slug = models.SlugField("URL nomi", unique=True, help_text="Lotin harflarda, masalan: arxan-park")
    status = models.CharField("Holati", max_length=20, choices=Status.choices, default=Status.BUILDING)
    klass = models.CharField("Toifa", max_length=20, choices=Klass.choices, default=Klass.BUSINESS)
    tagline = models.CharField("Qisqa shior", max_length=160, blank=True)
    description = models.TextField("Tavsif", help_text="Xatboshilarni bo'sh qator bilan ajrating")
    features = models.TextField("Afzalliklar", blank=True, help_text="Har biri yangi qatorda")
    address = models.CharField("Manzil", max_length=255)
    latitude = models.DecimalField("Kenglik (lat)", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("Uzunlik (lng)", max_digits=9, decimal_places=6, null=True, blank=True)
    price_m2 = models.PositiveBigIntegerField("1 m² narxi, so'm", null=True, blank=True,
                                           help_text="Xonadon narxi = maydon × shu narx (xonadonga alohida narx yozilmagan bo'lsa). "
                                                     "Kalkulyatorlar ham shundan hisoblaydi")
    color = models.CharField("Asosiy rang", max_length=7, default="#B85C38", validators=[HEX_COLOR],
                             help_text="Loyiha sahifasi shu rangga o'tadi")
    cover = image_field("projects/", SIZE_COVER, verbose_name="Karta rasmi", blank=True)
    hero = image_field("projects/hero/", SIZE_HERO, verbose_name="Hero fon rasmi", blank=True)
    logo = image_field("projects/logo/", SIZE_LOGO, verbose_name="Logo (xarita belgisi)", blank=True)
    # Loyiha haqida: rasm YOKI video — faqat bittasi
    about_image = image_field("projects/about/", SIZE_ABOUT, verbose_name="«Loyiha haqida» rasmi", blank=True)
    about_video = models.FileField("«Loyiha haqida» videosi", upload_to="projects/video/", blank=True,
                                   validators=[VIDEO_EXT, max_40mb], help_text="MP4/WebM, 40 MB gacha, ovozsiz takrorlanadi")
    stat_blocks = models.PositiveSmallIntegerField("Bloklar soni", null=True, blank=True,
                                                   help_text="Bo'sh qolsa bloklardan hisoblanadi")
    stat_queues = models.PositiveSmallIntegerField("Navbatlar soni", null=True, blank=True)
    lobby_title = models.CharField("Lobbi sarlavhasi", max_length=120, blank=True, default="Nafis lobbi")
    lobby_text = models.TextField("Lobbi matni", blank=True)
    lobby_image = image_field("projects/lobby/", SIZE_LOBBY, verbose_name="Lobbi rasmi", blank=True)
    office = models.ForeignKey("SalesOffice", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="projects", verbose_name="Savdo ofisi")
    floors = models.PositiveSmallIntegerField("Qavatlar", null=True, blank=True)
    flats = models.PositiveIntegerField("Xonadonlar soni", null=True, blank=True)
    area = models.PositiveIntegerField("Umumiy maydon, m²", null=True, blank=True)
    handover = models.CharField("Topshirish muddati", max_length=60, blank=True, help_text="Masalan: 2027, IV chorak")
    live_url = models.URLField("Jonli kamera (embed havola)", blank=True,
                               help_text="Qurilish maydoni kamerasining iframe havolasi")
    tour_url = models.URLField("3D tur havolasi", blank=True)
    genplan = image_field("projects/genplan/", verbose_name="Genplan rasmi", blank=True,
                          help_text="Majmuaning yuqoridan ko'rinishi. Binolar shu rasm ustiga joylashtiriladi")
    is_published = models.BooleanField("Saytda ko'rinsin", default=True)
    order = models.PositiveSmallIntegerField("Tartib", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "Loyiha"
        verbose_name_plural = "Loyihalar"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"{settings.SITE_URL}/loyihalar/{self.slug}"

    def clean(self):
        if self.about_image and self.about_video:
            raise ValidationError({"about_video": "«Loyiha haqida» uchun rasm yoki video — faqat bittasini yuklang"})


class ArchItem(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="arch_items")
    title = models.CharField("Sarlavha", max_length=120)
    text = models.TextField("Izoh", blank=True)
    image = image_field("projects/arch/", SIZE_ARCH, verbose_name="Rasm", blank=True)
    order = models.PositiveSmallIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Arxitektura kartasi"
        verbose_name_plural = "Arxitektura"


class InteriorSlide(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="interior_slides")
    title = models.CharField("Sarlavha", max_length=120)
    text = models.TextField("Matn", blank=True)
    image = image_field("projects/interior/", SIZE_INTERIOR, verbose_name="Rasm")
    order = models.PositiveSmallIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Ichki makon slaydi"
        verbose_name_plural = "Ichki makon"


LUCIDE_ICONS = [
    ("arrow-up-down", "Lift"), ("door-closed", "Eshik"), ("panel-top", "Vitraj"), ("lamp-ceiling", "Yoritish"),
    ("shield-check", "Xavfsizlik"), ("cctv", "Kamera"), ("car", "Avtoturargoh"), ("trees", "Ko'kalamzor"),
    ("baby", "Bolalar"), ("dumbbell", "Sport"), ("wifi", "Internet"), ("thermometer-sun", "Isitish"),
    ("sofa", "Lounge"), ("package", "Pochta qutilari"), ("accessibility", "Qulay kirish"), ("sparkles", "Boshqa"),
]


class LobbyFeature(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="lobby_features")
    icon = models.CharField("Ikonka", max_length=30, choices=LUCIDE_ICONS, default="sparkles")
    label = models.CharField("Nomi", max_length=60)
    order = models.PositiveSmallIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Lobbi afzalligi"
        verbose_name_plural = "Lobbi afzalliklari"


class InfraPoint(models.Model):
    class Category(models.TextChoices):
        SCHOOL = "talim", "Maktab va universitet"
        KINDER = "bogcha", "Bolalar bog'chasi"
        MEDIC = "tibbiyot", "Tibbiyot"
        SHOP = "savdo", "Savdo markazi"
        LEISURE = "dam", "Dam olish joyi"
        SPORT = "sport", "Sport"
        CAFE = "kafe", "Kafe va restoran"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="infra_points")
    category = models.CharField("Toifa", max_length=20, choices=Category.choices)
    name = models.CharField("Nomi", max_length=120)
    latitude = models.DecimalField("Kenglik", max_digits=9, decimal_places=6)
    longitude = models.DecimalField("Uzunlik", max_digits=9, decimal_places=6)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Infratuzilma nuqtasi"
        verbose_name_plural = "Infratuzilma"


class ProjectImage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="images")
    image = image_field("projects/gallery/", verbose_name="Rasm")
    caption = models.CharField("Izoh", max_length=160, blank=True)
    order = models.PositiveSmallIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Rasm"
        verbose_name_plural = "Galereya"


class CatalogPage(models.Model):
    """Loyiha katalogi (buklet) — saytda kitobdek varaqlanadi. Sahifalar raqami bo'yicha: 1, 2, 3…"""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="catalog_pages")
    image = image_field("projects/catalog/", verbose_name="Sahifa rasmi", width_field="width", height_field="height",
                        help_text="Hamma sahifalar bir xil o'lchamda bo'lsin (masalan 1600×1130). JPG/PNG/WebP, 8 MB gacha")
    width = models.PositiveIntegerField(null=True, editable=False)
    height = models.PositiveIntegerField(null=True, editable=False)
    order = models.PositiveSmallIntegerField("Sahifa raqami", default=0, blank=True,
                                             help_text="Bo'sh yoki 0 qolsa — keyingi raqam o'zi beriladi")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Katalog sahifasi"
        verbose_name_plural = "Katalog (kitob)"

    def __str__(self):
        return f"{self.order}-sahifa"

    def save(self, *args, **kwargs):
        if not self.order:  # bittalab qo'shilganda avtomatik 1, 2, 3…
            last = CatalogPage.objects.filter(project_id=self.project_id).aggregate(m=models.Max("order"))["m"]
            self.order = (last or 0) + 1
        super().save(*args, **kwargs)


PERCENT = [MaxValueValidator(100)]


class Building(models.Model):
    """Majmuadagi blok/bo'lim. Genplan rasmida (x%, y%) nuqtada ko'rsatiladi."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="buildings", verbose_name="Loyiha")
    number = models.PositiveSmallIntegerField("Blok raqami")
    floors = models.PositiveSmallIntegerField("Qavatlar soni")
    queue = models.PositiveSmallIntegerField("Navbat", default=1)
    completion_year = models.PositiveSmallIntegerField("Topshirish yili", null=True, blank=True)
    plan_x = models.DecimalField("Genplanda X, %", max_digits=5, decimal_places=2, default=50, validators=PERCENT)
    plan_y = models.DecimalField("Genplanda Y, %", max_digits=5, decimal_places=2, default=50, validators=PERCENT)

    class Meta:
        ordering = ["project", "number"]
        unique_together = [("project", "number")]
        verbose_name = "Blok"
        verbose_name_plural = "Bloklar"

    def __str__(self):
        return f"{self.project} — {self.number}-blok"


class FloorPlan(models.Model):
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="floor_plans")
    floor = models.SmallIntegerField("Qavat")
    image = image_field("plans/floors/", verbose_name="Qavat rejasi")

    class Meta:
        ordering = ["floor"]
        unique_together = [("building", "floor")]
        verbose_name = "Qavat rejasi"
        verbose_name_plural = "Qavat rejalari"


class Flat(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "sotuvda", "Sotuvda"
        BOOKED = "band", "Band qilingan"
        SOLD = "sotilgan", "Sotilgan"

    class Kind(models.TextChoices):
        RESIDENTIAL = "turar", "Turar-joy"
        COMMERCIAL = "tijorat", "Tijorat"

    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="flats", verbose_name="Blok")
    number = models.CharField("Xonadon raqami", max_length=12)
    kind = models.CharField("Turi", max_length=10, choices=Kind.choices, default=Kind.RESIDENTIAL)
    rooms = models.PositiveSmallIntegerField("Xonalar soni")
    area = models.DecimalField("Maydon, m²", max_digits=6, decimal_places=2)
    floor = models.SmallIntegerField("Qavat")
    price = models.PositiveBigIntegerField("Narx, so'm", null=True, blank=True)
    show_price = models.BooleanField("Narxni saytda ko'rsatish", default=False,
                                     help_text="O'chiq bo'lsa narx saytga umuman yuborilmaydi — «So'rov bo'yicha»")
    status = models.CharField("Holati", max_length=10, choices=Status.choices, default=Status.AVAILABLE)
    plan = image_field("plans/flats/", verbose_name="Xonadon rejasi", blank=True)

    class Meta:
        ordering = ["building", "floor", "number"]
        unique_together = [("building", "number")]
        indexes = [models.Index(fields=["status", "rooms", "floor"])]
        verbose_name = "Xonadon"
        verbose_name_plural = "Xonadonlar"

    def __str__(self):
        return f"№{self.number} · {self.rooms} xona · {self.area} m²"


class FlatLayout(models.Model):
    """Xonadon turi: loyihadagi bir xil xonali va bir xil maydondagi BARCHA xonadonlar uchun rasmlar va tavsif.

    Xonadonga bog'lanmaydi — saytda (loyiha, xonalar, maydon) bo'yicha topiladi. Shuning uchun 176 ta xonadonga
    rasmni bittalab emas, har bir turga bir marta yuklash kifoya.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="layouts", verbose_name="Loyiha")
    rooms = models.PositiveSmallIntegerField("Xonalar soni")
    area = models.DecimalField("Maydon, m²", max_digits=6, decimal_places=2)
    description = models.TextField("Tavsif", blank=True,
                                    help_text="Xonadon sahifasida rasmlar yonida chiqadi. Xatboshilarni bo'sh qator bilan ajrating.")
    # Rejadagi raqamlar tartibida: [{"name": "Dahliz", "area": 11.51}, ...] — saytda reja ostida ro'yxat bo'lib chiqadi
    parts = models.JSONField("Xonalar tarkibi", default=list, blank=True)

    class Meta:
        ordering = ["project", "rooms", "area"]
        unique_together = [("project", "rooms", "area")]
        verbose_name = "Xonadon turi"
        verbose_name_plural = "Xonadon turlari"

    def __str__(self):
        return f"{self.project} — {self.rooms} xona, {self.area} m²"

    def clean(self):
        """Xonalar ro'yxati: nomi (40 belgigacha) va maydoni (0–200 m²), ko'pi bilan 15 ta."""
        rows = [] if self.parts in (None, "") else self.parts  # formada bo'sh ro'yxat None bo'lib keladi
        rows = rows if isinstance(rows, list) else None
        if rows is None or len(rows) > 15:
            raise ValidationError({"parts": "Xonalar ro'yxati noto'g'ri"})
        clean = []
        for r in rows:
            name = " ".join(str((r or {}).get("name", "")).split())[:40] if isinstance(r, dict) else ""
            try:
                area = round(float(str(r.get("area", "")).replace(",", ".")), 2)
            except (TypeError, ValueError, AttributeError):
                area = None
            if not name and area is None:
                continue  # bo'sh qator
            if not name or area is None or not 0 < area < 200:
                raise ValidationError({"parts": f"«{name or '—'}»: nomi va maydoni (m²) to'g'ri bo'lsin"})
            clean.append({"name": name, "area": area})
        self.parts = clean


class FlatLayoutImage(models.Model):
    layout = models.ForeignKey(FlatLayout, on_delete=models.CASCADE, related_name="images")
    image = image_field("plans/layouts/", verbose_name="Rasm")
    caption = models.CharField("Izoh", max_length=160, blank=True, help_text="Masalan: Mehmonxona, Oshxona")
    order = models.PositiveSmallIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Xonadon rasmi"
        verbose_name_plural = "Xonadon rasmlari"


class SalesOffice(models.Model):
    name = models.CharField("Nomi", max_length=120, help_text="Masalan: Markaziy sotuv ofisi")
    address = models.CharField("Manzil", max_length=255)
    phone = models.CharField("Telefon", max_length=32, blank=True)
    hours = models.CharField("Ish vaqti", max_length=120, blank=True)
    latitude = models.DecimalField("Kenglik", max_digits=9, decimal_places=6, null=True, blank=True,
                                   help_text="Bo'sh qolsa xarita va «Qanday yetib borish» manzil bo'yicha qidiradi")
    longitude = models.DecimalField("Uzunlik", max_digits=9, decimal_places=6, null=True, blank=True)
    photo = image_field("offices/", SIZE_OFFICE, verbose_name="Ofis surati (xarita belgisi)", blank=True)
    order = models.PositiveSmallIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Sotuv ofisi"
        verbose_name_plural = "Sotuv ofislari"

    def __str__(self):
        return self.name


class Post(models.Model):
    class Kind(models.TextChoices):
        NEWS = "yangilik", "Yangilik"
        BUILD = "qurilish", "Qurilish jarayoni"
        PARTNER = "hamkorlik", "Hamkorlik"
        PHOTO = "foto", "Fotoreportaj"
        VIDEO = "video", "Video"

    title = models.CharField("Sarlavha", max_length=200)
    slug = models.SlugField("URL nomi", unique=True, max_length=220)
    kind = models.CharField("Turi", max_length=20, choices=Kind.choices, default=Kind.NEWS)
    cover = image_field("posts/", verbose_name="Muqova rasmi", blank=True)
    excerpt = models.CharField("Qisqa matn", max_length=300, blank=True)
    body = models.TextField("Matn", blank=True, help_text="Xatboshilarni bo'sh qator bilan ajrating")
    video_url = models.URLField("YouTube havola", blank=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="posts", verbose_name="Loyiha")
    published_at = models.DateTimeField("Sana", default=timezone.now)
    is_published = models.BooleanField("Saytda ko'rinsin", default=True)

    class Meta:
        ordering = ["-published_at"]
        verbose_name = "Material"
        verbose_name_plural = "Media"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"{settings.SITE_URL}/media/{self.slug}"


class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    image = image_field("posts/gallery/", verbose_name="Rasm")
    order = models.PositiveSmallIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Rasm"
        verbose_name_plural = "Galereya"


class Appeal(models.Model):
    class Kind(models.TextChoices):
        APPEAL = "murojaat", "Murojaat"
        CALL = "qongiroq", "Qo'ng'iroq so'rovi"
        FOREIGN = "chet_el", "Chet ellik mijoz"

    class State(models.TextChoices):
        NEW = "yangi", "Yangi"
        SEEN = "korildi", "Ko'rildi"
        DONE = "hal_qilindi", "Hal qilindi"

    class Source(models.TextChoices):
        """Saytning qaysi formasidan kelgani — Telegramda kategoriya bo'lib ko'rinadi."""
        HOME = "bosh_sahifa", "Bosh sahifa"
        PROJECT = "loyiha", "Loyiha sahifasi"
        FLAT = "xonadon", "Xonadon sahifasi"
        APPEAL = "murojaat", "Murojaat"
        CONTACT = "aloqa", "Aloqa"
        FOREIGN = "chet_el", "Chet elliklar uchun"
        REQUEST = "ariza", "Ariza (tepadagi tugma)"

    class Applicant(models.TextChoices):
        PERSON = "mijoz", "Mijoz"
        COMPANY = "kompaniya", "Kompaniya"

    kind = models.CharField("Turi", max_length=20, choices=Kind.choices, default=Kind.APPEAL)
    source = models.CharField("Qayerdan", max_length=20, choices=Source.choices, blank=True)
    applicant = models.CharField("Kim", max_length=10, choices=Applicant.choices, default=Applicant.PERSON)
    company = models.CharField("Kompaniya", max_length=200, blank=True)
    inn = models.CharField("STIR (INN)", max_length=20, blank=True)
    doc_number = models.CharField("Hujjat raqami", max_length=60, blank=True)
    name = models.CharField("Ism", max_length=120)
    phone = models.CharField("Telefon", max_length=32)
    email = models.EmailField("Email", blank=True)
    subject = models.CharField("Mavzu", max_length=200, blank=True)
    message = models.TextField("Xabar", blank=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Loyiha")
    flat = models.ForeignKey("Flat", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Xonadon")
    country = models.CharField("Davlat", max_length=80, blank=True)
    state = models.CharField("Holati", max_length=20, choices=State.choices, default=State.NEW)
    note = models.TextField("Ichki izoh", blank=True)
    created_at = models.DateTimeField("Kelgan vaqti", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Murojaat"
        verbose_name_plural = "Murojaatlar"

    def __str__(self):
        return f"{self.name} — {self.phone}"


class SiteSettings(models.Model):
    """Yagona yozuv: kontaktlar, ijtimoiy tarmoqlar, kompaniya haqida."""

    phone = models.CharField("Telefon", max_length=32, blank=True,
                             help_text="Bo'sh qolsa saytda telefon ko'rsatilmaydi")
    email = models.EmailField("Email", default="info@arxan.uz")
    address = models.CharField("Ofis manzili", max_length=255, default="Samarqand shahri")
    latitude = models.DecimalField("Ofis kengligi", max_digits=9, decimal_places=6, null=True, blank=True,
                                   help_text="Bo'sh qolsa «Aloqa» sahifasida xarita ko'rsatilmaydi")
    longitude = models.DecimalField("Ofis uzunligi", max_digits=9, decimal_places=6, null=True, blank=True)
    work_hours = models.TextField("Ish vaqti", default="Du–Ju: 09:00–19:00\nSh–Ya: 10:00–18:00")
    telegram = models.URLField("Telegram", blank=True)
    instagram = models.URLField("Instagram", blank=True)
    facebook = models.URLField("Facebook", blank=True)
    youtube = models.URLField("YouTube", blank=True)
    about_title = models.CharField("Biz haqimizda — sarlavha", max_length=200,
                                   default="Shahar uchun puxta o'ylangan uylar quramiz")
    about_text = models.TextField("Biz haqimizda — matn", blank=True)
    founded_year = models.PositiveSmallIntegerField("Tashkil topgan yil", null=True, blank=True,
                                                    help_text="Bo'sh qolsa saytda tajriba yillari ko'rsatilmaydi")
    stat_projects = models.PositiveSmallIntegerField("Topshirilgan loyihalar", default=0)
    stat_families = models.PositiveIntegerField("Baxtli oilalar", default=0)
    stat_area = models.PositiveIntegerField("Qurilgan maydon, m²", default=0)

    class Meta:
        verbose_name = "Sayt sozlamalari"
        verbose_name_plural = "Sayt sozlamalari"

    def __str__(self):
        return "Sayt sozlamalari"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Milestone(models.Model):
    """«Biz haqimizda» → «Kompaniya tarixi» slayderi: yillar bo'yicha voqealar."""

    year = models.PositiveSmallIntegerField("Yil")
    title = models.CharField("Voqea", max_length=200)
    text = models.CharField("Izoh", max_length=300, blank=True)
    image = image_field("history/", verbose_name="Rasm", blank=True,
                        help_text="Gorizontal rasm, masalan 1600×1000. Bo'sh qolsa chizma ko'rsatiladi")

    class Meta:
        ordering = ["-year", "-id"]
        verbose_name = "Tarixiy sana"
        verbose_name_plural = "Kompaniya tarixi"

    def __str__(self):
        return f"{self.year} — {self.title}"


class Activity(models.Model):
    """«Biz haqimizda» → «Kompaniyaning faoliyati»: mukofotlar, sertifikatlar, ko'rgazmalar."""

    year = models.PositiveSmallIntegerField("Yil")
    organization = models.CharField("Tashkilot", max_length=120, blank=True,
                                    help_text="Kim tomonidan, masalan: O'zbekiston Marketing Assotsiatsiyasi")
    title = models.CharField("Nomi", max_length=200, help_text="Masalan: «Yil brendi» mukofoti")
    image = image_field("activities/", verbose_name="Rasm (ixtiyoriy)", blank=True)

    class Meta:
        ordering = ["-year", "-id"]
        verbose_name = "Faoliyat"
        verbose_name_plural = "Kompaniya faoliyati"

    def __str__(self):
        return f"{self.year} — {self.title}"


class TwoFactor(models.Model):
    """Panelga kirish uchun ikkinchi bosqich: autentifikator ilovasi kodi (TOTP)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="two_factor")
    secret = models.CharField(max_length=64)
    confirmed = models.BooleanField(default=False)
    last_step = models.BigIntegerField(default=0)  # bir kodni ikki marta ishlatmaslik uchun

    class Meta:
        verbose_name = "2 bosqichli tekshiruv"
        verbose_name_plural = "2 bosqichli tekshiruv"


# ---------- Panelga Telegram bot orqali kirish ----------

def normalize_phone(raw: str) -> str:
    """Har qanday yozuvni «+998901234567» ko'rinishiga keltiradi; tanib bo'lmasa — bo'sh qator."""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if len(digits) == 9:
        digits = "998" + digits
    return f"+{digits}" if len(digits) == 12 and digits.startswith("998") else ""


class PanelAccess(models.Model):
    """Panelga kirishga ruxsat berilgan telefon raqam. Kirish faqat shu raqam egasining Telegram'i orqali."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin (botda /admin ham ishlaydi)"
        STAFF = "xodim", "Xodim (faqat panelga kiradi)"

    full_name = models.CharField("Ism-familiya", max_length=120)
    phone = models.CharField("Telefon", max_length=16, unique=True, help_text="+998901234567")
    role = models.CharField("Huquq", max_length=8, choices=Role.choices, default=Role.STAFF)
    telegram_id = models.BigIntegerField("Telegram ID", null=True, blank=True, unique=True, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                editable=False, related_name="panel_access")
    added_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                                 verbose_name="Kim qo'shgan")
    created_at = models.DateTimeField("Qo'shilgan", auto_now_add=True)
    last_login_at = models.DateTimeField("Oxirgi kirish", null=True, blank=True, editable=False)

    class Meta:
        ordering = ("role", "full_name")
        verbose_name = "Panelga ruxsat"
        verbose_name_plural = "Panelga ruxsatlar"

    def __str__(self):
        return f"{self.full_name} ({self.phone})"

    def clean(self):
        phone = normalize_phone(self.phone)
        if not phone:
            raise ValidationError({"phone": "Raqam +998XXXXXXXXX ko'rinishida bo'lsin"})
        self.phone = phone

    def save(self, *args, **kwargs):
        self.phone = normalize_phone(self.phone) or self.phone
        if self.user_id is None:
            # Har bir ruxsatga parolsiz panel foydalanuvchisi: parol bilan kirib bo'lmaydi
            # (raqam avval o'chirilib, qayta qo'shilsa — o'sha foydalanuvchi qayta yoqiladi)
            from django.contrib.auth import get_user_model
            user, _ = get_user_model().objects.get_or_create(username=f"tg{self.phone.lstrip('+')}")
            user.first_name, user.is_staff, user.is_active = self.full_name[:150], True, True
            user.set_unusable_password()
            user.save()
            self.user = user
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        user = self.user
        super().delete(*args, **kwargs)
        if user is not None:
            # Ochiq panel sessiyalari ham darhol yaroqsiz bo'ladi (token parol hash'iga bog'langan)
            user.is_active = False
            user.set_unusable_password()
            user.save(update_fields=["is_active", "password"])


class PanelLoginLink(models.Model):
    """Bot bergan bir martalik kirish havolasi (5 daqiqa). Bazada faqat token hash'i saqlanadi."""

    access = models.ForeignKey(PanelAccess, on_delete=models.CASCADE, related_name="links")
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class PanelLoginEvent(models.Model):
    """Bot va panel orqali kirish urinishlari — /admin statistikasi shundan."""

    class Kind(models.TextChoices):
        REQUEST = "sorov", "Raqam yubordi (ruxsat bor)"
        DENIED = "rad", "Raqam yubordi (ruxsat yo'q)"
        LINK = "havola", "Kirish havolasi oldi"
        LOGIN = "kirish", "Panelga kirdi"

    kind = models.CharField("Hodisa", max_length=8, choices=Kind.choices)
    access = models.ForeignKey(PanelAccess, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Kim")
    phone = models.CharField("Telefon", max_length=16, blank=True)
    telegram_id = models.BigIntegerField("Telegram ID", null=True, blank=True)
    name = models.CharField("Telegramdagi ismi", max_length=120, blank=True)
    ip = models.CharField("IP", max_length=64, blank=True)
    created_at = models.DateTimeField("Vaqt", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Kirish tarixi"
        verbose_name_plural = "Kirish tarixi"
