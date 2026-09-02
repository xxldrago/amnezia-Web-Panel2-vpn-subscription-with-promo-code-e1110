# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Системные зависимости для SSH (paramiko) и работы с сертификатами
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Зависимости только самой Amnezia Web Panel (FastAPI/uvicorn)
COPY requirements-panel.txt .
RUN pip install --no-cache-dir -r requirements-panel.txt

# Копирование кода панели
COPY app.py .
COPY connection_service.py .
COPY managers/ managers/
COPY telegram_bot.py .
COPY templates/ templates/
COPY static/ static/
COPY translations/ translations/
COPY protocol_telemt/ protocol_telemt/

# Директории для данных
RUN mkdir -p data instance logs

EXPOSE 5000

# Панель сама запускает uvicorn (учитывает собственный SSL в настройках panel)
CMD ["python", "app.py"]
