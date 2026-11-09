# Arxan — serverga chiqarish (arxan.uz)

Hammasi Docker'da ishlaydi: **nginx** (SSL, himoya) → **Next** (sayt va /panel) → **Django** (baza) + **Telegram bot**.
Kod uchta GitHub repozitoriyda turadi, server ularni `git clone` qiladi.

```
/opt/arxan/
  qurilish/        ← qurilish_git      (backend + server/ — shu papka)
  qurilish_next/   ← qurilish_next_git (sayt)
  qurilish_bot/    ← qurilish_bot_git  (bot)
  data/            ← baza, rasmlar, SSL (o'zi yaratiladi, git'ga tushmaydi)
```

## 0. Oldindan
- Ubuntu 22.04 yoki 24.04, kamida **2 GB RAM** va 20 GB disk.
- Domen DNS'ida ikkita **A** yozuv server IP'siga qaratilgan bo'lsin: `arxan.uz` va `www.arxan.uz`.

## 1. Serverga kerakli dasturlar (bir marta)
```bash
apt update && apt install -y git curl nano
curl -fsSL https://get.docker.com | sh
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw --force enable
```

## 2. Kodni yuklab olish (bir marta)
```bash
mkdir -p /opt/arxan && cd /opt/arxan
git clone https://github.com/Nodirbek2000-tat/qurilish_git.git qurilish
git clone https://github.com/Nodirbek2000-tat/qurilish_next_git.git qurilish_next
git clone https://github.com/Nodirbek2000-tat/qurilish_bot_git.git qurilish_bot
```

## 3. Ishga tushirish
```bash
cd /opt/arxan/qurilish/server
sh deploy.sh        # 1-marta: .env yasaydi
nano .env           # SSL_EMAIL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID ni yozing
sh deploy.sh        # quradi, Arxan Residence'ni yuklaydi, SSL oladi
docker compose exec -u app django python manage.py bot_admin "Ism Familiya" +998XXXXXXXXX
```
Tayyor bo'lgach: **https://arxan.uz**, panel: **https://arxan.uz/panel** (kirish Telegram bot orqali).

> ⚠️ Server ishga tushgach, kompyuterdagi botni o'chiring. Bitta token bilan ikkita bot bir vaqtda ishlay olmaydi.

## Yangilash (kod o'zgarganda)
Kompyuterda o'zgarishni GitHub'ga push qiling, keyin serverda:
```bash
cd /opt/arxan/qurilish/server && sh deploy.sh
```
U uchala repozitoriyni `git pull` qiladi va qayta quradi. Baza va rasmlarga tegmaydi.

## SSL (Let's Encrypt, 90 kun ≈ 3 oy, bepul)
- **O'zi yangilanadi:** certbot kuniga 2 marta tekshiradi. 30 kundan kam qolganda yangi 90 kunlik oladi.
- **Tugab qolsa:**
  ```bash
  cd /opt/arxan/qurilish/server && sh ssl.sh
  ```
- **Muddatidan qat'i nazar hozir yangisini olish:** `sh ssl.sh yangi`. Haftasiga 5 martadan ko'p ishlatmang, bu Let's Encrypt cheklovi.

## Kundalik buyruqlar (`/opt/arxan/qurilish/server` ichida)
| Nima | Buyruq |
|---|---|
| Holat | `docker compose ps` |
| Xatolarni ko'rish | `docker compose logs -f --tail 100 next` (yoki `django`, `bot`, `nginx`) |
| Qayta ishga tushirish | `docker compose restart` |
| Zaxira (baza + rasmlar) | `sh zaxira.sh` → `/opt/arxan/data/zaxira/` |
| Har kuni avtomatik zaxira | `crontab -e` → `0 3 * * * sh /opt/arxan/qurilish/server/zaxira.sh >/dev/null 2>&1` |
| Panelga admin qo'shish | `docker compose exec -u app django python manage.py bot_admin "Ism" +998901234567` |

## Himoya (nima qilingan)
- Faqat 80 va 443 portlar ochiq. 80-portga kelganlar https ga yo'naltiriladi. Begona domen yoki IP bilan kelgan skanerlar bilan ulanish uziladi.
- Bitta IP uchun cheklovlar:
  - sahifalar: sekundiga 20 ta so'rov;
  - forma va saqlash: sekundiga 2 ta;
  - bir vaqtda 50 ta ulanish.
- Django ham murojaatlarni cheklaydi: bitta IP'dan 10 daqiqada 5 tadan ko'p emas.
- `wp-admin`, `.env`, `.git`, `.php` kabi manzillarni qidiruvchi botlar javob olmaydi.
- Django API va kesh yangilash manzili tashqaridan yopiq.
- Panelga faqat Telegram bot bergan bir martalik havola orqali kiriladi (5 daqiqa).
- Konteynerlar root emas, alohida foydalanuvchi nomidan ishlaydi. Maxfiy kalitlar faqat serverdagi `.env` da saqlanadi va GitHub'ga tushmaydi.
- `server/boshlangich/` da faqat sayt kontenti bor: loyiha, xonadonlar va rasmlar. Mijozlar murojaatlari, telefonlar va kirish tarixi unga kiritilmagan.
