# Телеграм-бот store (aiogram 3). Самостоятельный контейнер.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Общий requirements (Flask+SQLAlchemy) + клиент БД + aiogram
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir aiogram==3.4.1

# Код store
COPY . .

# data.json панели монтируется во время запуска
ENV PANEL_DATA_FILE=/panel-data/data.json

CMD ["python", "-m", "bot.vpn_telegram_bot"]