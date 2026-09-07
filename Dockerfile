# Dockerfile do RAILWAY (produção). Contexto de build = raiz do repo.
# Roda `start.sh`, que sobe Celery worker+beat em background — por isso
# instala `postgresql-client` (o `pg_dump` do bloco MIGRATE_FROM_URL).
# NÃO é o mesmo que `backend/Dockerfile`: aquele serve ao Docker Compose,
# onde Celery são serviços separados. Os dois divergem de propósito.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-por \
    poppler-utils \
    libpq-dev \
    postgresql-client \
    gcc \
    curl \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --upgrade pip wheel setuptools
RUN pip install --prefer-binary -r requirements.txt

COPY backend/ .

EXPOSE 8000
# start.sh: Celery worker+beat em background + uvicorn em foreground (o
# railway.toml usa o mesmo comando; este CMD é o default fora do Railway).
CMD ["sh", "start.sh"]
