#!/bin/sh
# nginx uchun SSL fayllarini tayyorlaydi.
#  - Let's Encrypt sertifikati bo'lsa, o'shani ishlatadi
#  - hali bo'lmasa (birinchi ishga tushirish), vaqtinchalik sertifikat yasaydi,
#    shunda nginx ishga tushadi va ssl.sh haqiqiy sertifikatni oladi
set -e
DIR=/etc/nginx/ssl
LIVE=/etc/letsencrypt/live/$DOMAIN
mkdir -p "$DIR"

if [ -f "$LIVE/fullchain.pem" ] && [ -f "$LIVE/privkey.pem" ]; then
  ln -sf "$LIVE/fullchain.pem" "$DIR/fullchain.pem"
  ln -sf "$LIVE/privkey.pem" "$DIR/privkey.pem"
  echo "40-ssl: Let's Encrypt sertifikati ishlatilmoqda ($DOMAIN)"
elif [ ! -f "$DIR/privkey.pem" ]; then
  command -v openssl >/dev/null 2>&1 || apk add --no-cache openssl >/dev/null
  openssl req -x509 -nodes -newkey rsa:2048 -days 2 -subj "/CN=$DOMAIN" \
    -keyout "$DIR/privkey.pem" -out "$DIR/fullchain.pem" >/dev/null 2>&1
  echo "40-ssl: vaqtinchalik sertifikat yaratildi — ./ssl.sh ni ishga tushiring"
fi
