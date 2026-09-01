# 🎁 Модуль тестовой подписки VPN

## Обзор

Добавлена возможность предоставления **бесплатной тестовой подписки на 3 дня** для всех пользователей. Каждый пользователь может активировать тестовую подписку **только один раз**.

## Функционал

### Возможности
- ✅ Бесплатная тестовая подписка на **3 дня**
- ✅ Доступ ко **всем серверам** панели
- ✅ **Однократная** активация на пользователя
- ✅ Автоматическая выдача доступов через `vpn_auto_provision.py`
- ✅ Интеграция с Platega.io (без оплаты)
- ✅ Красивый UI баннер на странице покупки

## Как это работает

### 1. Пользователь видит баннер
```
┌─────────────────────────────────────────────────┐
│  🎁 Попробуйте бесплатно!                       │
│  Получите тестовую подписку на все сервера     │
│  на 3 дня. Доступно только один раз.           │
│                                                 │
│  [🚀 Активировать тестовый период]             │
└─────────────────────────────────────────────────┘
```

### 2. После активации
- Создаётся заказ со статусом `paid` и `is_trial: True`
- Запись сохраняется в `trial_subscriptions` (data.json)
- Запускается авто-выдача доступов на всех серверах
- Пользователь перенаправляется в личный кабинет

### 3. Проверка повторной активации
Система проверяет:
```python
if user_has_used_trial(user_id):
    return "Вы уже использовали тестовую подписку"
```

## API Endpoints

### GET `/vpn/my-orders`
Возвращает информацию о доступности тестовой подписки:
```json
{
  "orders": [...],
  "trial_used": false,
  "trial_available": true
}
```

### POST `/vpn/activate_trial`
Активирует тестовую подписку:
```json
// Request
POST /vpn/activate_trial
Content-Type: application/json

// Response (success)
{
  "success": true,
  "order_id": "TRIAL_123_20250115123456",
  "days": 3,
  "message": "Тестовая подписка на 3 дня активирована! Доступы создаются..."
}

// Response (error)
{
  "success": false,
  "error": "Вы уже использовали тестовую подписку"
}
```

## Структура данных

### Trial Order (в vpn_purchases)
```json
{
  "order_id": "TRIAL_123_20250115123456",
  "user_id": 123,
  "username": "john",
  "plan_id": "trial",
  "plan_label": "Тестовая подписка на все сервера",
  "days": 3,
  "base_price": 0,
  "final_price": 0,
  "payment_method": "trial",
  "status": "paid",
  "is_trial": true,
  "provisioned": false,
  "created_at": "2025-01-15T12:34:56",
  "expires_at": "2025-01-18T12:34:56"
}
```

### Trial Subscription Record
```json
{
  "user_id": 123,
  "username": "john",
  "order_id": "TRIAL_123_20250115123456",
  "activated_at": "2025-01-15T12:34:56",
  "expires_at": "2025-01-18T12:34:56",
  "days": 3
}
```

## Конфигурация

### vpn_purchase.py
```python
TRIAL_SUBSCRIPTION = {
    "days": 3,
    "description": "Тестовая подписка на все сервера",
    "one_per_user": True,
}
```

### vpn_auto_provision.py
Добавлен план `trial` в маппинг длительности:
```python
mapping = {
    '15_days': 15,
    '1_month': 30,
    '3_months': 90,
    '6_months': 180,
    '12_months': 365,
    'trial': 3  # Тестовая подписка на 3 дня
}
```

## Интеграция

### 1. Убедитесь, что модули подключены
```python
# В app.py
from vpn_purchase import setup_vpn_purchase_module
from vpn_auto_provision import setup_auto_provisioning

setup_vpn_purchase_module(app)
setup_auto_provisioning(app, db.engine, VpnPurchase)
```

### 2. Добавьте ссылку в личном кабинете
```html
<!-- my_connections.html -->
<a href="/vpn/purchase" class="btn btn-primary">
  🛒 Купить VPN или активировать тестовый период
</a>
```

## Логирование

Модуль логирует все операции:
```
INFO - Trial subscription activated for user 123 (john), order: TRIAL_123_...
INFO - Начало авто-выдачи доступа для пользователя 123. План: trial, Срок: 3 дн.
INFO - Создание подключения для пользователя 123 на сервере Server1 (...)
INFO - Тестовая подписка TRIAL_123_... успешно активирована
```

## Безопасность

- ✅ Проверка `user_has_used_trial()` перед активацией
- ✅ Данные сохраняются в `data.json` для персистентности
- ✅ Защита от повторной активации после перезагрузки сервера

## Изменения в шаблонах

### templates/vpn_purchase.html
Добавлен баннер тестовой подписки:
```html
<div class="trial-banner" id="trialBanner" style="display: none;">
  <div class="trial-content">
    <span class="trial-icon">🎁</span>
    <div class="trial-text">
      <strong>Попробуйте бесплатно!</strong>
      <p>Получите тестовую подписку на все сервера на 3 дня...</p>
    </div>
    <button onclick="activateTrial()">🚀 Активировать тестовый период</button>
  </div>
</div>
```

JavaScript функция `activateTrial()`:
- Показывает подтверждение
- Отправляет POST запрос на `/vpn/activate_trial`
- Скрывает баннер при успехе
- Перенаправляет в личный кабинет

## Тестирование

### 1. Проверка доступности
```bash
curl http://localhost:8000/vpn/my-orders \
  --cookie "session=your_session_cookie"
```

### 2. Активация тестовой подписки
```bash
curl -X POST http://localhost:8000/vpn/activate_trial \
  --cookie "session=your_session_cookie" \
  -H "Content-Type: application/json"
```

### 3. Проверка повторной активации
Повторный вызов должен вернуть ошибку:
```json
{"success": false, "error": "Вы уже использовали тестовую подписку"}
```

## Отладка

Если тестовая подписка не активируется:

1. Проверьте логи приложения
2. Убедитесь, что `data.json` доступен для записи
3. Проверьте, что пользователь авторизован
4. Убедитесь, что `trial_subscriptions` не содержит запись для этого пользователя

## Миграция данных

При обновлении существующей установки:
- Новые поля добавляются автоматически
- Старые заказы остаются без изменений
- `trial_subscriptions` создаётся при первой активации

---

**Версия:** 1.0  
**Дата обновления:** 2025-01-15  
**Зависимости:** vpn_purchase.py, vpn_auto_provision.py
