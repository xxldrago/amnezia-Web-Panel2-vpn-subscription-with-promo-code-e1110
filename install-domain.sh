#!/bin/bash

# ===========================================
# VPN Panel - Автоматическая установка на домен
# ===========================================
# Скрипт для развертывания панели на VPS с Ubuntu
# Поддержка SSL через Let's Encrypt
# ===========================================

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Логирование
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Проверка прав root
if [ "$EUID" -ne 0 ]; then 
    log_error "Запустите скрипт от root: sudo ./install.sh"
    exit 1
fi

# ===========================================
# ВВОД ДОМЕНА
# ===========================================
echo ""
echo "============================================"
echo "  VPN Panel - Установка на домен"
echo "============================================"
echo ""

read -p "Введите ваш домен (например: vpn.example.com): " DOMAIN
if [ -z "$DOMAIN" ]; then
    log_error "Домен не указан!"
    exit 1
fi

read -p "Введите email администратора: " ADMIN_EMAIL
if [ -z "$ADMIN_EMAIL" ]; then
    log_error "Email не указан!"
    exit 1
fi

read -p "Введите пароль администратора: " -s ADMIN_PASSWORD
echo ""
if [ -z "$ADMIN_PASSWORD" ]; then
    log_error "Пароль не указан!"
    exit 1
fi

# ===========================================
# ПРОВЕРКА DOCKER
# ===========================================
log_info "Проверка Docker..."

if ! command -v docker &> /dev/null; then
    log_warning "Docker не найден. Устанавливаем..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    log_success "Docker установлен"
else
    log_success "Docker найден: $(docker --version)"
fi

if ! command -v docker-compose &> /dev/null; then
    log_warning "Docker Compose не найден. Устанавливаем..."
    apt-get update
    apt-get install -y docker-compose-plugin
    log_success "Docker Compose установлен"
else
    log_success "Docker Compose найден: $(docker compose version)"
fi

# ===========================================
# ГЕНЕРАЦИЯ SECRET KEY
# ===========================================
log_info "Генерация секретного ключа..."
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
log_success "Secret key сгенерирован"

# ===========================================
# СОЗДАНИЕ .ENV ФАЙЛА
# ===========================================
log_info "Создание файла .env..."

cat > .env << EOF
# База данных
DB_USER=vpnuser
DB_PASSWORD=$(openssl rand -base64 24)
DB_NAME=vpndb

# Безопасность
SECRET_KEY=${SECRET_KEY}

# Домен
DOMAIN=${DOMAIN}
BASE_URL=https://${DOMAIN}

# Platega.io (заполните позже в админ-панели)
PLATEGA_MERCHANT_ID=
PLATEGA_SECRET_KEY=

# SMTP (заполните позже в админ-панели)
SMTP_SERVER=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=

# Приложение
FLASK_ENV=production
DEBUG=False

# Администратор
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
EOF

chmod 600 .env
log_success "Файл .env создан"

# ===========================================
# ПОДГОТОВКА ДИРЕКТОРИЙ
# ===========================================
log_info "Подготовка директорий..."

mkdir -p nginx/conf.d
mkdir -p certbot/www
mkdir -p certbot/conf
mkdir -p data
mkdir -p instance
mkdir -p uploads

chmod -R 755 nginx certbot data instance uploads
log_success "Директории созданы"

# ===========================================
# НАСТРОЙКА NGINX
# ===========================================
log_info "Настройка Nginx..."

cat > nginx/conf.d/default.conf << EOF
server {
    listen 80;
    server_name ${DOMAIN};
    
    # ACME challenge для Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    # Проксирование на приложение
    location / {
        proxy_pass http://app:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }
}
EOF

log_success "Nginx настроен"

# ===========================================
# ЗАПУСК КОНТЕЙНЕРОВ
# ===========================================
log_info "Запуск контейнеров..."

docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d --build

log_success "Контейнеры запущены"

# ===========================================
# ПОЛУЧЕНИЕ SSL СЕРТИФИКАТА
# ===========================================
echo ""
log_info "Получение SSL сертификата Let's Encrypt..."
echo ""

# Ждем готовности приложения
sleep 10

# Получаем сертификат
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email ${ADMIN_EMAIL} \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d ${DOMAIN}

if [ $? -eq 0 ]; then
    log_success "SSL сертификат получен"
    
    # Обновляем конфигурацию Nginx для HTTPS
    cat > nginx/conf.d/default.conf << EOF
# HTTP - редирект на HTTPS
server {
    listen 80;
    server_name ${DOMAIN};
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name ${DOMAIN};
    
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    
    # SSL настройки
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    location / {
        proxy_pass http://app:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }
}
EOF
    
    # Перезапускаем Nginx
    docker compose restart nginx
    
    log_success "HTTPS настроен"
else
    log_error "Не удалось получить SSL сертификат"
    log_warning "Панель доступна по HTTP (порт 80)"
    log_warning "Попробуйте получить сертификат вручную:"
    log_warning "docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d ${DOMAIN}"
fi

# ===========================================
# ЗАВЕРШЕНИЕ
# ===========================================
echo ""
echo "============================================"
log_success "Установка завершена!"
echo "============================================"
echo ""
echo "🌐 Ваш сайт: https://${DOMAIN}"
echo "📧 Email администратора: ${ADMIN_EMAIL}"
echo ""
echo "📝 Полезные команды:"
echo "   docker compose ps              - Статус контейнеров"
echo "   docker compose logs -f app     - Логи приложения"
echo "   docker compose logs -f nginx   - Логи Nginx"
echo "   docker compose restart         - Перезапуск всех сервисов"
echo "   docker compose down            - Остановка всех сервисов"
echo ""
echo "🔧 Для изменения настроек:"
echo "   1. Отредактируйте файл .env"
echo "   2. Выполните: docker compose up -d"
echo ""
echo "🎁 Настройте платежную систему и email:"
echo "   Зайдите в админ-панель → Настройки"
echo ""
echo "============================================"
echo ""
