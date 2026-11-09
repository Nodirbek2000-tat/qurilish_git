#!/bin/sh
# Ishga tushishda: /data papkasini tayyorlaydi, migratsiya qiladi, keyin oddiy foydalanuvchi
# (root emas) nomidan ishlaydi.
set -e
mkdir -p /data/media /data/zaxira "$DJANGO_CACHE_DIR"
# Faqat Django'ga tegishli fayllar (data/certbot ga tegilmaydi)
chown app:app /data
chown -R app:app /data/media /data/zaxira "$DJANGO_CACHE_DIR"
for f in /data/db.sqlite3 /data/db.sqlite3-wal /data/db.sqlite3-shm; do
  if [ -e "$f" ]; then chown app:app "$f"; fi
done

if [ "$1" = "gunicorn" ]; then
  setpriv --reuid=app --regid=app --init-groups python manage.py migrate --noinput
fi
exec setpriv --reuid=app --regid=app --init-groups "$@"
