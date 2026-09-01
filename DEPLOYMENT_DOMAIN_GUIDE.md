# 🚀 VPN Panel - Полная инструкция по установке на домен

## 📋 Требования

- VPS с Ubuntu 20.04+ (рекомендуется 22.04)
- Домен, направленный на IP вашего сервера (A запись)
- Открытые порты: 80 (HTTP), 443 (HTTPS)
- root доступ к серверу
- Минимум 1GB RAM, 2 ядра CPU

---

## 🔧 Быстрая установка (1 команда)

### Шаг 1: Подключитесь к серверу по SSH

```bash
ssh root@ваш-server-ip
```

### Шаг 2: Скачайте и запустите скрипт установки

```bash
# Клонируйте репозиторий (или скачайте файлы)
git clone <URL-ВАШЕГО-РЕПОЗИТОРИЯ> /opt/vpn-panel
cd /opt/vpn-panel

# Сделайте скрипт исполняемым
chmod +x install-domain.sh

# Запустите установку
./install-domain.sh
```

### Шаг 3: Введите данные

Скрипт запросит:
- **Домен**: `vpn.example.com` (должен указывать на IP сервера)
- **Email администратора**: `admin@example.com`
- **Пароль администратора**: придумайте надежный пароль

### Шаг 4: Готово!

После завершения установки вы получите:
```
🌐 Ваш сайт: https://vpn.example.com
📧 Email администратора: admin@example.com
```

---

## 📦 Что устанавливается автоматически

| Компонент | Версия | Назначение |
|-----------|--------|------------|
| **Docker** | latest | Контейнеризация |
| **PostgreSQL** | 15-alpine | База данных |
| **Nginx** | alpine | Веб-сервер + SSL |
| **Certbot** | latest | SSL сертификаты Let's Encrypt |
| **Flask App** | Python 3.11 | Основное приложение |

---

## 🔐 SSL сертификат

Скрипт автоматически:
1. Получает SSL сертификат от Let's Encrypt
2. Настраивает редирект HTTP → HTTPS
3. Добавляет security headers (HSTS, X-Frame-Options и др.)
4. Настраивает автообновление сертификата (каждые 12 часов)

---

## 🛠️ Управление сервисами

### Проверка статуса

```bash
docker compose ps
```

### Просмотр логов

```bash
# Все логи
docker compose logs -f

# Только приложение
docker compose logs -f app

# Только Nginx
docker compose logs -f nginx

# Только база данных
docker compose logs -f db
```

### Перезапуск

```bash
# Все сервисы
docker compose restart

# Отдельный сервис
docker compose restart app
```

### Остановка

```bash
docker compose down
```

### Обновление

```bash
# После изменения кода или .env
docker compose up -d --build
```

---

## ⚙️ Настройка после установки

### 1. Вход в админ-панель

Откройте в браузере: `https://ваш-домен.ru`

Войдите под учетными данными, указанными при установке.

### 2. Настройка платежной системы

Перейдите в **Админ-панель → Настройки** и заполните:
- `PLATEGA_MERCHANT_ID` - ваш Merchant ID из Platega.io
- `PLATEGA_SECRET_KEY` - ваш Secret Key из Platega.io

### 3. Настройка email уведомлений

В **Настройках** укажите SMTP данные:
- SMTP сервер (например, `smtp.gmail.com`)
- Порт (обычно `587`)
- Email и пароль приложения
- Email отправителя

> Для Gmail используйте "App Password": https://myaccount.google.com/apppasswords

### 4. Настройка тарифов

В **Настройках** измените цены на тарифы VPN:
- 15 дней
- 1 месяц
- 3 месяца
- 6 месяцев
- 12 месяцев

### 5. Настройка реферальной системы

В **Настройках** измените:
- Бонус новому пользователю
- Бонус пригласившему
- Процент комиссии с пополнений

---

## 📁 Структура файлов

```
/opt/vpn-panel/
├── .env                    # Переменные окружения (не редактировать вручную)
├── .env.example            # Шаблон переменных
├── docker-compose.yml      # Конфигурация Docker
├── Dockerfile              # Образ приложения
├── nginx/
│   └── conf.d/
│       └── default.conf    # Конфигурация Nginx
├── certbot/
│   ├── www/                # ACME challenges
│   └── conf/               # SSL сертификаты
├── data/                   # Данные приложения
├── instance/               # Файлы Flask
└── uploads/                # Загруженные файлы
```

---

## 🔒 Безопасность

### Рекомендации

1. **Смените пароль администратора** после первого входа
2. **Настройте Firewall**:
   ```bash
   ufw allow 22/tcp    # SSH
   ufw allow 80/tcp    # HTTP
   ufw allow 443/tcp   # HTTPS
   ufw enable
   ```

3. **Обновляйте систему регулярно**:
   ```bash
   apt update && apt upgrade -y
   ```

4. **Используйте сложные пароли** в `.env`

5. **Ограничьте доступ к базе данных**:
   - PostgreSQL доступен только внутри Docker сети
   - Нет внешних портов

---

## 🆘 Troubleshooting

### Сертификат не получился

Проверьте, что домен указывает на IP сервера:
```bash
ping ваш-домен.ru
```

Получите сертификат вручную:
```bash
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email admin@ваш-домен.ru \
  -d ваш-домен.ru
```

### Приложение не запускается

Проверьте логи:
```bash
docker compose logs -f app
```

Пересоберите образ:
```bash
docker compose up -d --build --force-recreate
```

### Ошибка базы данных

Проверьте статус PostgreSQL:
```bash
docker compose logs -f db
```

Перезапустите базу:
```bash
docker compose restart db
```

### Port 80/443 уже занят

Остановите другие веб-серверы:
```bash
systemctl stop nginx
systemctl stop apache2
```

---

## 📊 Мониторинг

### Использование ресурсов

```bash
docker stats
```

### Место на диске

```bash
df -h
docker system df
```

### Очистка старых образов

```bash
docker system prune -a
```

---

## 🔄 Резервное копирование

### База данных

```bash
docker compose exec db pg_dump -U vpnuser vpndb > backup_$(date +%Y%m%d).sql
```

### Все данные

```bash
tar -czf backup_$(date +%Y%m%d).tar.gz data/ instance/ uploads/ .env
```

### Восстановление

```bash
# База данных
cat backup_20240101.sql | docker compose exec -T db psql -U vpnuser vpndb

# Файлы
tar -xzf backup_20240101.tar.gz
```

---

## 📞 Поддержка

При возникновении проблем:

1. Проверьте логи: `docker compose logs -f`
2. Убедитесь, что домен настроен правильно
3. Проверьте доступность портов 80 и 443
4. Создайте тикет в техподдержку через панель

---

## 🎯 Следующие шаги

После установки:

1. ✅ Войдите в админ-панель
2. ✅ Настройте Platega.io для оплаты
3. ✅ Настройте SMTP для email уведомлений
4. ✅ Измените тарифы на VPN
5. ✅ Настройте реферальную программу
6. ✅ Добавьте серверы VPN
7. ✅ Протестируйте покупку подписки
8. ✅ Активируйте тестовый период

**Готово!** Ваша VPN панель готова к работе! 🎉
