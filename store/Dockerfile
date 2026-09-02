# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# store пакет в /app/store (контекст сборки = каталог store/)
COPY . /app/store/

ENV PYTHONPATH=/app
# Монтируем общий data.json панели (доступ только на чтение для модулей)
ENV PANEL_DATA_FILE=/panel-data/data.json

EXPOSE 5150

# Запуск через gunicorn (2 воркера)
CMD ["gunicorn", "--bind", "0.0.0.0:5150", "--workers", "2", "--threads", "2", "--timeout", "120", "store.app:create_app()"]