# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка пакетов
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всего кода
COPY . .

# Создаем директории для данных
RUN mkdir -p data instance logs

# !!! ВАЖНО: Запускаем скрипт интеграции перед стартом сервера !!!
# Он автоматически пропатчит app.py, добавив все модули
RUN python auto_integrate.py

# Экспортируем порт
EXPOSE 5000

# Запуск через Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "app:app"]
