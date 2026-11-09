#!/bin/sh
# SSL sertifikat — Let's Encrypt, har biri 90 kun (3 oy). Bepul.
#
#   sh ssl.sh        sertifikat yo'q bo'lsa oladi; tugagan yoki 30 kundan kam qolgan bo'lsa
#                    yangi 90 kunlik oladi; hali ko'p kun bo'lsa tegmaydi
#   sh ssl.sh yangi  muddatidan qat'i nazar HOZIR yangi 90 kunlik oladi
#                    (Let's Encrypt cheklovi: haftasiga 5 martadan ko'p emas)
#
# Eslatma: buni qo'lda yozish shart emas — certbot konteyneri kuniga 2 marta tekshirib,
# muddati yaqinlashganda o'zi yangilaydi. Bu buyruq — «tugab qolsa» degan holat uchun.
set -e
cd "$(dirname "$0")"

val() { sed -n "s/^$1=//p" .env | tail -n 1 | tr -d '\r"'"'"; }
[ -f .env ] || { echo "Xato: .env yo'q. Avval sh deploy.sh ni ishga tushiring."; exit 1; }
DOMAIN=$(val DOMAIN)
EMAIL=$(val SSL_EMAIL)
[ -n "$DOMAIN" ] || { echo "Xato: .env da DOMAIN yozilmagan"; exit 1; }

certbot() { docker compose run --rm --entrypoint certbot certbot "$@"; }

mkdir -p ../../data/certbot/conf ../../data/certbot/www
docker compose up -d nginx >/dev/null   # Let's Encrypt tekshiruvi 80-port orqali o'tadi

if docker compose run --rm --entrypoint sh certbot -c "test -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem"; then
  if [ "$1" = "yangi" ]; then
    echo ">> $DOMAIN: yangi 90 kunlik sertifikat olinmoqda (majburiy)..."
    certbot renew --cert-name "$DOMAIN" --force-renewal --non-interactive
  else
    echo ">> $DOMAIN: muddat tekshirilmoqda (30 kundan kam qolgan bo'lsa yangilanadi)..."
    certbot renew --cert-name "$DOMAIN" --non-interactive
  fi
else
  [ -n "$EMAIL" ] || { echo "Xato: .env da SSL_EMAIL yozilmagan"; exit 1; }
  DOMAINS="-d $DOMAIN"
  if getent hosts "www.$DOMAIN" >/dev/null 2>&1; then
    DOMAINS="$DOMAINS -d www.$DOMAIN"
  else
    echo "Diqqat: www.$DOMAIN DNS da yo'q — sertifikat faqat $DOMAIN uchun olinadi."
  fi
  echo ">> $DOMAIN: birinchi sertifikat olinmoqda..."
  # --agree-tos: Let's Encrypt shartlariga rozilik (https://letsencrypt.org/repository/)
  certbot certonly --webroot -w /var/www/certbot $DOMAINS --cert-name "$DOMAIN" \
    --email "$EMAIL" --agree-tos --no-eff-email --non-interactive --key-type ecdsa
fi

# nginx yangi sertifikatni darhol o'qisin (saytni o'chirmasdan)
docker compose exec -T nginx sh -c 'sh /arxan-ssl.sh && nginx -s reload'

echo
certbot certificates --cert-name "$DOMAIN" 2>/dev/null | grep -E "Domains|Expiry" || true
echo ">> Tayyor: https://$DOMAIN"
