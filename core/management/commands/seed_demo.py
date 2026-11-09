"""Namunaviy ma'lumotlar: saytni darhol ko'rish uchun. Panelda o'zgartirib/o'chirib yuborasiz.

    python manage.py seed_demo
"""

import io
import random
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from core.models import (ArchItem, Building, Flat, InfraPoint, LobbyFeature, Milestone, Post, Project, SalesOffice,
                         SiteSettings)

# Har bir loyiha uchun bloklarning genplandagi joyi (x%, y%) va topshirish yili
LAYOUTS = {
    "arxan-park": ([(22, 30), (50, 24), (78, 30), (30, 70), (70, 70)], 2027),
    "arxan-riverside": ([(25, 40), (50, 32), (75, 40)], 2028),
    "arxan-citadel": ([(35, 45), (65, 45)], 2028),
    "arxan-bog": ([(25, 35), (55, 30), (80, 55), (40, 72)], 2023),
}

OFFICES = [
    ("Markaziy sotuv ofisi", "Toshkent sh., Mirobod tumani, Amir Temur ko'chasi", 41.3030, 69.2790),
    ("Arxan Park sotuv ofisi", "Toshkent sh., Yunusobod tumani", 41.3640, 69.2885),
]

ARCH = [
    ("Materiallar", "Fasadlar keramogranit va issiqlikni saqlovchi klinker bilan qoplangan — yillar o'tsa ham rangini yo'qotmaydi."),
    ("Eksteryer", "Yuqori qavatlardagi ochiq terrasalar va vitraj oynalar binoga yengillik va yorug'lik beradi."),
    ("Qulaylik", "Kirish guruhlari ko'cha sathida, zinapoyasiz. Bolalar aravachasi va nogironlar aravachasi uchun qulay."),
]
LOBBY = [("arrow-up-down", "Tezkor liftlar"), ("door-closed", "Metall eshiklar"),
         ("panel-top", "Vitraj derazalar"), ("lamp-ceiling", "Mayin yoritish")]
INFRA = [  # (toifa, nomi, lat siljishi, lng siljishi)
    ("talim", "Maktab", 0.004, -0.003), ("talim", "Litsey", -0.006, 0.005), ("bogcha", "Bolalar bog'chasi", 0.002, 0.004),
    ("bogcha", "Xususiy bog'cha", -0.003, -0.005), ("tibbiyot", "Oilaviy poliklinika", 0.006, 0.002),
    ("tibbiyot", "Dorixona", -0.001, 0.003), ("savdo", "Savdo markazi", -0.007, -0.002), ("savdo", "Supermarket", 0.001, -0.004),
    ("dam", "Shahar bog'i", 0.008, -0.006), ("sport", "Fitnes klub", -0.004, 0.007), ("sport", "Futbol maydoni", 0.005, 0.008),
    ("kafe", "Kofexona", 0.0015, 0.0015), ("kafe", "Restoran", -0.005, 0.001),
]


def genplan_png(points, color: str) -> bytes:
    """Demo uchun yuqoridan ko'rinish: yo'laklar, ko'kalamzor va bino izlari."""
    w, h = 1600, 1000
    img = Image.new("RGB", (w, h), "#e9e6df")
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((60, 60, w - 60, h - 60), 40, fill="#dfe6d6")
    for x in range(160, w - 100, 230):
        d.line((x, 80, x - 60, h - 80), fill="#efece5", width=26)
    d.line((60, h * 0.52, w - 60, h * 0.48), fill="#efece5", width=34)
    rnd = random.Random(len(points))
    for _ in range(70):
        cx, cy, r = rnd.randint(90, w - 90), rnd.randint(90, h - 90), rnd.randint(10, 22)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="#b9c9a8")
    for px, py in points:
        cx, cy = px / 100 * w, py / 100 * h
        d.rectangle((cx - 120 + 14, cy - 70 + 18, cx + 120 + 14, cy + 70 + 18), fill="#c9c4b9")
        d.rectangle((cx - 120, cy - 70, cx + 120, cy + 70), fill="#fbfaf7", outline=color, width=6)
        for i in range(1, 6):
            d.line((cx - 120 + i * 40, cy - 70, cx - 120 + i * 40, cy + 70), fill="#e6e1d8", width=2)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()

PROJECTS = [
    dict(slug="arxan-park", title="Arxan Park", status="qurilmoqda", klass="biznes", color="#2F5D50",
         tagline="Shahar markazida yashil hovli", address="Toshkent sh., Yunusobod tumani",
         latitude=41.3645, longitude=69.2870, floors=16, flats=420, area=58000,
         handover="2027, II chorak", order=1,
         features="Yopiq hovli — mashinasiz\nYer osti avtoturargohi\nBolalar va sport maydonchalari\nDizaynerlik lobbilari\n24/7 qo'riqlash va videokuzatuv"),
    dict(slug="arxan-riverside", title="Arxan Riverside", status="sotuvda", klass="premium", color="#1F3A5F",
         tagline="Daryo bo'yidagi sokin hayot", address="Toshkent sh., Mirzo Ulug'bek tumani",
         latitude=41.3380, longitude=69.3350, floors=22, flats=310, area=64000,
         handover="2028, I chorak", order=2,
         features="O'z sohil bo'yi promenadasi\nPanoramali oynalar\nFitnes va SPA\nKonsyerj xizmati\nAqlli uy tizimi"),
    dict(slug="arxan-citadel", title="Arxan Citadel", status="qurilmoqda", klass="premium", color="#7A4E2D",
         tagline="Tarixiy markazdagi zamonaviy qal'a", address="Toshkent sh., Shayxontohur tumani",
         latitude=41.3260, longitude=69.2280, floors=12, flats=180, area=31000,
         handover="2028, IV chorak", order=3,
         features="Klub tipidagi uy\nTom terrasasi\nShaxsiy omborxonalar\nAvtomobil uchun zaryadlash"),
    dict(slug="arxan-bog", title="Arxan Bog'", status="topshirilgan", klass="komfort", color="#5C6B3A",
         tagline="Oilalar uchun qulay mahalla", address="Toshkent sh., Chilonzor tumani",
         latitude=41.2750, longitude=69.2040, floors=9, flats=260, area=27000,
         handover="Topshirilgan", order=4,
         features="Maktab va bog'cha yonida\nKeng bolalar maydonchasi\nMetroga 5 daqiqa"),
]

DESCRIPTION = (
    "{title} — puxta o'ylangan rejalar, sifatli materiallar va obod hudud uyg'unligi. "
    "Har bir xonadon tabiiy yorug'lik va qulaylikni hisobga olib loyihalangan.\n\n"
    "Hovli avtomobillardan xoli: bolalar xavfsiz o'ynaydi, kattalar esa yashil maydonda dam oladi. "
    "Birinchi qavatlarda kundalik ehtiyojlar uchun do'konlar va kafelar joylashadi.\n\n"
    "Qurilish jarayonini saytimizda va ijtimoiy tarmoqlarimizda muntazam yoritib boramiz."
)

POSTS = [
    ("arxan-park-karkas-12-qavat", "Arxan Park: karkas 12-qavatga yetdi", "qurilish", "arxan-park",
     "Monolit ishlar jadvaldan oldinda borayapti."),
    ("riverside-taqdimoti", "Arxan Riverside taqdimoti bo'lib o'tdi", "foto", "arxan-riverside",
     "Yangi premium loyiha mehmonlarga ilk bor ko'rsatildi."),
    ("arxan-bog-kalitlar", "Arxan Bog' aholisi kalitlarni qabul qilmoqda", "yangilik", "arxan-bog",
     "260 oila yangi uylariga ko'chib o'tishni boshladi."),
    ("citadel-poydevor", "Arxan Citadel: poydevor ishlari boshlandi", "qurilish", "arxan-citadel",
     "Tarixiy markazdagi yangi loyihada qurilish start oldi."),
    ("ochiq-eshiklar-kuni", "Ochiq eshiklar kuni: namunaviy xonadon", "foto", "arxan-park",
     "Mehmonlar tayyor ta'mirli namunaviy xonadonni ko'rishdi."),
    ("kompaniya-yil-yakunlari", "Arxan: yil yakunlari va rejalar", "yangilik", None,
     "O'tgan yil natijalari va kelgusi loyihalar haqida."),
    ("bank-bilan-hamkorlik", "Yetakchi bank bilan ipoteka bo'yicha hamkorlik", "hamkorlik", None,
     "Mijozlarimiz uchun qulay ipoteka shartlari."),
]

MILESTONES = [
    (2012, "Kompaniya tashkil topdi", "Kichik jamoa va katta maqsad bilan boshladik"),
    (2015, "Birinchi turar-joy majmuasi topshirildi", "120 oila yangi uyga ko'chdi"),
    (2019, "1000-oila", "Mijozlarimiz soni mingtadan oshdi"),
    (2023, "Arxan Bog' topshirildi", "Komfort toifadagi 260 xonadon"),
    (2026, "Uchta yangi loyiha", "Park, Riverside va Citadel qurilishi"),
]


class Command(BaseCommand):
    help = "Namunaviy loyihalar, yangiliklar va sozlamalar yaratadi"

    def handle(self, *args, **opts):
        s = SiteSettings.load()
        s.about_text = (
            "Arxan — Toshkentdagi turar-joy quruvchi kompaniya. Biz uylarni emas, yashash muhitini quramiz: "
            "har bir loyihada arxitektura, hovli va infratuzilma bir butun bo'lib o'ylanadi.\n\n"
            "Sifat, muddatga rioya va ochiqlik — ishimizning uch asosi. Qurilish jarayonini doimo "
            "mijozlarimizga ko'rsatib boramiz."
        )
        s.stat_projects, s.stat_families, s.stat_area = 9, 2400, 420000
        s.address = "Toshkent sh., Mirobod tumani"
        s.save()

        for data in PROJECTS:
            Project.objects.update_or_create(
                slug=data["slug"], defaults={**data, "description": DESCRIPTION.format(title=data["title"])})

        now = timezone.now()
        for i, (slug, title, kind, project, excerpt) in enumerate(POSTS):
            Post.objects.update_or_create(slug=slug, defaults=dict(
                title=title, kind=kind, excerpt=excerpt,
                project=Project.objects.filter(slug=project).first() if project else None,
                body=f"{excerpt}\n\n{DESCRIPTION.format(title='Loyiha')}",
                published_at=now - timedelta(days=i * 9)))

        for year, title, text in MILESTONES:
            Milestone.objects.get_or_create(year=year, title=title, defaults={"text": text})

        for i, (name, address, lat, lng) in enumerate(OFFICES):
            SalesOffice.objects.update_or_create(name=name, defaults=dict(
                address=address, latitude=lat, longitude=lng, phone=s.phone,
                hours="Du–Sh: 09:00–19:00", order=i))

        with transaction.atomic():
            self._buildings_and_flats()
            self._sections()

        self.stdout.write(self.style.SUCCESS("Namunaviy ma'lumotlar tayyor"))

    def _sections(self):
        office = SalesOffice.objects.first()
        for p in Project.objects.all():
            Project.objects.filter(pk=p.pk).update(
                office=office,
                lobby_text=(f"{p.title} lobbisi — mehmonlarni kutib oluvchi ikkinchi mehmonxona: baland shift, tabiiy tosh, "
                            "yumshoq yorug'lik va hovliga to'g'ridan-to'g'ri chiqish."))
            if not p.arch_items.exists():
                ArchItem.objects.bulk_create(ArchItem(project=p, title=t, text=x, order=i) for i, (t, x) in enumerate(ARCH))
            if not p.lobby_features.exists():
                LobbyFeature.objects.bulk_create(LobbyFeature(project=p, icon=ic, label=l, order=i) for i, (ic, l) in enumerate(LOBBY))
            if p.latitude and not p.infra_points.exists():
                InfraPoint.objects.bulk_create(
                    InfraPoint(project=p, category=c, name=n, latitude=round(float(p.latitude) + dy, 6),
                               longitude=round(float(p.longitude) + dx, 6)) for c, n, dy, dx in INFRA)

    def _buildings_and_flats(self):
        rnd = random.Random(42)
        room_mix = [1, 2, 3, 2, 4, 1]
        base_area = {1: 38, 2: 58, 3: 82, 4: 112}
        for project in Project.objects.filter(slug__in=LAYOUTS):
            points, year = LAYOUTS[project.slug]
            if not project.genplan:
                project.genplan.save(f"{project.slug}.png", ContentFile(genplan_png(points, project.color)), save=True)
            done = project.status == Project.Status.DONE
            for n, (x, y) in enumerate(points, start=1):
                b, created = Building.objects.update_or_create(project=project, number=n, defaults=dict(
                    floors=project.floors or 12, queue=1 if n <= 2 else 2, plan_x=x, plan_y=y,
                    completion_year=year if n <= 2 else year + (0 if done else 1)))
                if not created and b.flats.exists():
                    continue
                flats = []
                per_floor = 4 if n % 2 else 6
                for floor in range(2, b.floors + 1):
                    for k in range(per_floor):
                        rooms = room_mix[(k + floor) % len(room_mix)]
                        area = round(base_area[rooms] + rnd.uniform(-4, 9), 2)
                        roll = rnd.random()
                        status = (Flat.Status.SOLD if done or roll < 0.22
                                  else Flat.Status.BOOKED if roll < 0.34 else Flat.Status.AVAILABLE)
                        price = int(area * rnd.randint(12, 17) * 1_000_000)
                        flats.append(Flat(building=b, number=str((floor - 2) * per_floor + k + 1), rooms=rooms,
                                          area=area, floor=floor, price=price, show_price=rnd.random() < 0.4,
                                          status=status))
                # 1-qavat — tijorat binolari
                for k in range(2):
                    flats.append(Flat(building=b, number=f"T{k + 1}", kind=Flat.Kind.COMMERCIAL, rooms=1,
                                      area=round(rnd.uniform(70, 160), 2), floor=1, status=Flat.Status.AVAILABLE))
                Flat.objects.bulk_create(flats)
