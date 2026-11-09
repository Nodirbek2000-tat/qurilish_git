#!/bin/sh
# Arxan — serverga o'rnatish va yangilash. Bitta buyruq (qurilish/server ichida):   sh deploy.sh
#
# 1-marta: .env yasaydi (maxfiy kalitlarni o'zi yaratadi), siz token va emailni yozasiz,
#          keyin yana sh deploy.sh. U hammasini quradi, Arxan Residence ma'lumotlarini yuklaydi
#          va SSL oladi.
# Keyingi safar: GitHub'dan yangi kodni oladi (git pull) va qayta chiqaradi.
#                Baza va rasmlar (/opt/arxan/data) saqlanib qoladi.
#
# Butun skript bitta funksiya ichida: git pull shu faylni o'zgartirsa ham ishlayotgani buzilmaydi.

SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

main() {
  set -e
  cd "$(dirname "$SELF")"
  ROOT=$(cd ../.. && pwd)          # /opt/arxan
  DATA="$ROOT/data"
  chmod +x ssl.sh zaxira.sh 2>/dev/null || true

  command -v docker >/dev/null || { echo "Xato: Docker o'rnatilmagan. Qarang: SERVER.md"; exit 1; }
  docker compose version >/dev/null 2>&1 || { echo "Xato: 'docker compose' yo'q. Qarang: SERVER.md"; exit 1; }

  # ---- 0. GitHub'dan yangi kod ----
  if [ "$1" != "--pulled" ]; then
    for repo in qurilish qurilish_next qurilish_bot; do
      if [ -d "$ROOT/$repo/.git" ]; then
        echo ">> git pull: $repo"
        git -C "$ROOT/$repo" pull --ff-only
      else
        echo "Xato: $ROOT/$repo yo'q. SERVER.md dagi git clone buyruqlarini bajaring."; exit 1
      fi
    done
    exec sh "$SELF" --pulled         # yangilangan skript bilan davom etamiz
  fi

  val() { sed -n "s/^$1=//p" .env | tail -n 1 | tr -d '\r"'"'"; }
  rand() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

  # ---- 1. .env ----
  if [ ! -f .env ]; then
    cp .env.example .env
    sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(rand 40)|" .env
    sed -i "s|^PANEL_PATH=.*|PANEL_PATH=boshqaruv-$(rand 16)|" .env
    sed -i "s|^SITE_API_KEY=.*|SITE_API_KEY=$(rand 32)|" .env
    sed -i "s|^REVALIDATE_SECRET=.*|REVALIDATE_SECRET=$(rand 32)|" .env
    sed -i "s|^BOT_API_KEY=.*|BOT_API_KEY=$(rand 32)|" .env
    chmod 600 .env
    echo
    echo ".env yaratildi. Endi oching va SSL_EMAIL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID ni yozing:"
    echo "    nano .env"
    echo "Keyin yana:  sh deploy.sh"
    exit 0
  fi
  for k in DOMAIN SSL_EMAIL TELEGRAM_BOT_TOKEN DJANGO_SECRET_KEY PANEL_PATH SITE_API_KEY REVALIDATE_SECRET BOT_API_KEY; do
    [ -n "$(val $k)" ] || { echo "Xato: .env da $k bo'sh. nano .env bilan to'ldiring."; exit 1; }
  done
  DOMAIN=$(val DOMAIN)

  # ---- 2. Papkalar; 1-marta — Arxan Residence ma'lumotlari ----
  mkdir -p "$DATA/media" "$DATA/certbot/conf" "$DATA/certbot/www" "$DATA/zaxira"
  FRESH=0
  if [ ! -f "$DATA/db.sqlite3" ]; then
    FRESH=1
    cp -rn boshlangich/media/. "$DATA/media/"
    cp boshlangich/arxan.json "$DATA/boshlangich.json"
  fi

  # ---- 3. Qurish va ishga tushirish ----
  echo ">> Qurilmoqda (birinchi marta 3-6 daqiqa)..."
  docker compose build --pull
  docker compose up -d --remove-orphans

  wait_healthy() {
    i=0
    while [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q "$1")" 2>/dev/null)" != "healthy" ]; do
      i=$((i + 1))
      [ $i -gt 60 ] && { echo "Xato: $1 ishga tushmadi. Ko'rish: docker compose logs $1"; exit 1; }
      sleep 3
    done
  }
  echo ">> Tekshirilmoqda..."
  wait_healthy django

  if [ "$FRESH" = 1 ]; then
    echo ">> Arxan Residence ma'lumotlari yuklanmoqda..."
    docker compose exec -T -u app django python manage.py loaddata /data/boshlangich.json
    rm -f "$DATA/boshlangich.json"
  fi

  wait_healthy next
  docker compose exec -T -u app django python manage.py kesh_yangila

  # ---- 4. SSL: birinchi marta olinadi, keyin certbot o'zi yangilaydi ----
  if ! docker compose run --rm --entrypoint sh certbot -c "test -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem"; then
    sh ssl.sh
  fi

  docker image prune -f >/dev/null 2>&1 || true
  echo
  docker compose ps
  echo
  echo ">> Tayyor: https://$DOMAIN   (panel: https://$DOMAIN/panel)"
  if [ "$FRESH" = 1 ]; then
    echo ">> Panelga admin qo'shing:"
    echo "   docker compose exec -u app django python manage.py bot_admin \"Ism Familiya\" +998XXXXXXXXX"
  fi
}

main "$@"
