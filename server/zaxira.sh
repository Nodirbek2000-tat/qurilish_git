#!/bin/sh
# Baza va rasmlarning zaxira nusxasi:   sh zaxira.sh
# /opt/arxan/data/zaxira/ ichiga sana bilan saqlanadi, oxirgi 14 tasi qoladi.
# Har kuni avtomatik qilish (crontab -e):   0 3 * * * sh /opt/arxan/qurilish/server/zaxira.sh >/dev/null 2>&1
set -e
cd "$(dirname "$0")"
DATA=../../data
D=$(date +%Y-%m-%d_%H%M)
mkdir -p $DATA/zaxira

# Sayt ishlab turganda ham to'g'ri nusxa (SQLite backup)
docker compose exec -T -u app django python -c "
import sqlite3
s = sqlite3.connect('/data/db.sqlite3'); d = sqlite3.connect('/data/zaxira/db_$D.sqlite3')
s.backup(d); d.close(); s.close()"
tar -czf "$DATA/zaxira/media_$D.tar.gz" -C $DATA media

# Eskilarini o'chirish (14 tadan ortig'i)
ls -1t $DATA/zaxira/db_*.sqlite3 2>/dev/null | tail -n +15 | xargs -r rm -f
ls -1t $DATA/zaxira/media_*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "Zaxira: $DATA/zaxira/db_$D.sqlite3, $DATA/zaxira/media_$D.tar.gz"
