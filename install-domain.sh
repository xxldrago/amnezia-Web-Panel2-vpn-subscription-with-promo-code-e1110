#!/bin/bash

# ===========================================
# VPN Panel - Автоматическая установка на домен
# ===========================================
# Разворачивает Amnezia Web Panel (FastAPI, порт 5000) в Docker,
# настраивает nginx на хосте как reverse proxy и выпускает SSL через Certbot.
# ===========================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [ "$EUID" -ne 0 ]; then
    log_error "Запустите скрипт от root: sudo bash install-domain.sh"
    exit 1
fi

# ===========================================
# ВВОД ДОМЕНА
# ===========================================
echo ""
echo "============================================"
echo "  Amnezia Web Panel - установка на домен"
echo "============================================"
echo ""

read -p "Введите ваш домен (например: panel.example.com): " DOMAIN
if [ -z "$DOMAIN" ]; then
    log_error "Домен не указан!"
    exit 1
fi

read -p "Введите email администратора (для Let's Encrypt): " ADMIN_EMAIL
if [ -z "$ADMIN_EMAIL" ]; then
    log_error "Email не указан!"
    exit 1
fi

# ===========================================
# ПРОВЕРКА/УСТАНОВКА DOCKER
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

if ! docker compose version &> /dev/null; then
    log_warning "Docker Compose не найден. Устанавливаем..."
    apt-get update
    apt-get install -y docker-compose-plugin
    log_success "Docker Compose установлен"
else
    log_success "Docker Compose найден: $(docker compose version)"
fi

# ===========================================
# УСТАНОВКА NGINX + CERTBOT (на хосте)
# ===========================================
log_info "Проверка nginx..."
if ! command -v nginx &> /dev/null; then
    log_warning "nginx не найден. Устанавливаем..."
    apt-get update
    apt-get install -y nginx
    log_success "nginx установлен"
else
    log_success "nginx найден: $(nginx -v 2>&1)"
fi

log_info "Проверка certbot..."
if ! command -v certbot &> /dev/null; then
    log_warning "certbot не найден. Устанавливаем..."
    apt-get update
    apt-get install -y certbot python3-certbot-nginx
    log_success "certbot установлен"
else
    log_success "certbot найден: $(certbot --version 2>&1)"
fi

# ===========================================
# ПОДГОТОВКА ФАЙЛОВ ДАННЫХ (для volume-монтирования)
# ===========================================
log_info "Подготовка файлов данных..."
mkdir -p instance logs
if [ ! -f data.json ]; then
    echo '{ }' > data.json
    log_success "Создан пустой data.json"
fi
if [ ! -f tunnels_state.json ]; then
    echo '{}' > tunnels_state.json
    log_success "Создан пустой tunnels_state.json"
fi

# ===========================================
# ЗАПУСК КОНТЕЙНЕРОВ ПАНЕЛИ
# ===========================================
log_info "Запуск контейнеров панели..."
docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d --build

# ===========================================
# НАСТРОЙКА NGINX (host)
# ===========================================
log_info "Настройка nginx..."

NGINX_CONF="/etc/nginx/sites-available/${DOMAIN}"
if [ ! -d /etc/nginx/sites-available ]; then
    mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
fi

cat > "${NGINX_CONF}" << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    # Вложенная Flask-система store (покупка, рефералка, тикеты)
    location /store/ {
        proxy_pass http://127.0.0.1:5150;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Amnezia Web Panel (FastAPI) — основная точка входа
    location / {
        proxy_pass http://127.0.0.1:5000;
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

ln -sf "${NGINX_CONF}" "/etc/nginx/sites-enabled/${DOMAIN}"

# Удаляем дефолтный сайт, если он есть, чтобы не конфликтовал
if [ -L /etc/nginx/sites-enabled/default ]; then
    rm -f /etc/nginx/sites-enabled/default
fi

# Проверка конфигурации
nginx -t && systemctl reload nginx

log_success "Nginx настроен на порт 80"

# ===========================================
# SSL ЧЕРЕЗ CERTBOT
# ===========================================
echo ""
log_info "Получение SSL сертификата Let's Encrypt..."
echo ""

certbot --nginx -d "${DOMAIN}" \
    --email "${ADMIN_EMAIL}" \
    --agree-tos \
    --no-eff-email \
    --redirect

# ===========================================
# ЗАВЕРШЕНИЕ
# ===========================================
echo ""
echo "============================================"
log_success "Установка завершена!"
echo "============================================"
echo ""
echo "🌐 Ваш сайт: https://${DOMAIN}"
echo ""
echo "📝 Полезные команды:"
echo "   docker compose ps              - Статус контейнеров"
echo "   docker compose logs -f panel   - Логи панели"
echo "   docker compose restart         - Перезапуск всех сервисов"
echo "   docker compose down            - Остановка всех сервисов"
echo ""
echo "🔐 Первичный вход в панель:"
echo "   Логин: admin"
echo "   Пароль: admin"
echo "   Смените пароль сразу после входа!"
echo ""
echo "============================================"