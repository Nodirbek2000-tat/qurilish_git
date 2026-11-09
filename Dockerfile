# Arxan — Django backend (gunicorn). Baza va yuklangan fayllar /data da (volume).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_DATA_DIR=/data \
    DJANGO_CACHE_DIR=/tmp/django-cache

WORKDIR /app
RUN useradd --uid 1000 --create-home app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "4", \
     "--timeout", "120", "--max-requests", "2000", "--max-requests-jitter", "200", \
     "--access-logfile", "-", "--forwarded-allow-ips", "*"]
