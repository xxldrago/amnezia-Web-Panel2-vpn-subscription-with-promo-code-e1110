# Модуль покупки VPN подписок с интеграцией Platega.io

Независимый модуль для покупки VPN подписок, который продолжает работать при обновлении основного кода приложения.

## 📋 Функционал

- **5 тарифных планов:**
  - 15 дней — 200₽
  - 1 месяц — 400₽
  - 3 месяца — 1100₽
  - 6 месяцев — 2100₽
  - 12 месяцев — 4000₽

- **Промокоды:**
  - WELCOME10 — скидка 10%
  - NEWUSER20 — скидка 20%
  - FRIEND15 — скидка 15%

- **Оплата через Platega.io:**
  - Создание платежной ссылки
  - Обработка callback'ов
  - Проверка статуса платежа

## 🔧 Интеграция в проект

### 1. Добавьте модуль в app.py

```python
from vpn_purchase import setup_vpn_purchase_module

# После создания app
setup_vpn_purchase_module(app)
```

### 2. Настройте переменные окружения

```bash
# .env файл или переменные окружения
PLATEGA_MERCHANT_ID=ваш_merchant_id_из_platega
PLATEGA_SECRET_KEY=ваш_secret_key_из_platega
```

> ⚠️ **Важно:** Пока вы не настроили реальные credentials, модуль работает в режиме симуляции.

### 3. Добавьте ссылку в личный кабинет

В файле `templates/my_connections.html` добавьте:

```html
<a href="/vpn/purchase" class="btn btn-primary">
    🛒 Купить VPN подписку
</a>
```

## 📡 API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/vpn/purchase` | Страница покупки VPN |
| POST | `/vpn/calculate` | Расчет цены с промокодом |
| POST | `/vpn/create_order` | Создание заказа |
| GET | `/vpn/my-orders` | История заказов пользователя |
| GET | `/vpn/payment/success` | Успешная оплата (redirect от Platega) |
| GET | `/vpn/payment/fail` | Неудачная оплата (redirect от Platega) |
| POST | `/vpn/platega/callback` | Webhook от Platega.io |

## 🔌 Platega.io Интеграция

### Аутентификация

Модуль использует заголовки для аутентификации в API Platega.io:

```
X-MerchantId: <ваш_merchant_id>
X-Secret: <ваш_secret_key>
```

### Создание платежной ссылки

При создании заказа модуль вызывает API Platega.io:

```python
POST https://app.platega.io/api/v1/payment-link/create

Headers:
  X-MerchantId: YOUR_MERCHANT_ID
  X-Secret: YOUR_SECRET_KEY

Body:
{
  "amount": 400,
  "currency": "RUB",
  "orderId": "VPN_123_20250101120000",
  "description": "VPN Subscription: 1 месяц",
  "successUrl": "https://yoursite.com/vpn/payment/success?order_id=...",
  "failUrl": "https://yoursite.com/vpn/payment/fail?order_id=...",
  "customer": {
    "email": "user@example.com",
    "name": "username"
  }
}
```

### Обработка callback'ов

Platega.io отправляет POST запрос на `/vpn/platega/callback`:

```json
{
  "transaction_id": "txn_123456",
  "order_id": "VPN_123_20250101120000",
  "status": "completed",
  "amount": 400
}
```

Статусы:
- `completed` / `paid` / `success` — оплата успешна
- `failed` / `cancelled` / `expired` — оплата не прошла

## 🗂️ Структура файлов

```
/workspace/
├── vpn_purchase.py              # Основной модуль
├── templates/
│   └── vpn_purchase.html        # Страница покупки
└── VPN_PURCHASE_MODULE_README.md # Эта документация
```

## 💾 Хранение данных

Заказы сохраняются в `data.json`:

```json
{
  "vpn_purchases": [
    {
      "order_id": "VPN_1_20250101120000",
      "user_id": 1,
      "username": "admin",
      "plan_id": "1_month",
      "plan_label": "1 месяц",
      "days": 30,
      "base_price": 400,
      "discount": 40,
      "final_price": 360,
      "promocode": "WELCOME10",
      "payment_method": "platega",
      "status": "paid",
      "created_at": "2025-01-01T12:00:00",
      "paid_at": "2025-01-01T12:05:00",
      "platega_transaction_id": "txn_123456",
      "payment_url": "https://app.platega.io/pay/..."
    }
  ]
}
```

## 🎨 Режимы работы

### Режим разработки (симуляция)

Если credentials не настроены:
```python
PLATEGA_MERCHANT_ID = 'YOUR_MERCHANT_ID_HERE'
PLATEGA_SECRET_KEY = 'YOUR_SECRET_KEY_HERE'
```

Модуль возвращает симулированную платежную ссылку и автоматически подтверждает платежи.

### Продакшен режим

После настройки реальных credentials модуль работает с реальным API Platega.io.

## 🔐 Безопасность

1. **Проверка подписи webhook** (закомментирована, раскомментируйте для продакшена):
```python
signature = request.headers.get('X-Platega-Signature')
expected_signature = hmac.new(
    PLATEGA_SECRET_KEY.encode(),
    json.dumps(data, sort_keys=True).encode(),
    hashlib.sha256
).hexdigest()
```

2. **Проверка статуса платежа** после возврата пользователя на success URL

3. **Валидация промокодов** с ограничением по использованию

## 📝 Changelog

### v1.1.0
- ✅ Добавлена полная интеграция с Platega.io
- ✅ Создание платежных ссылок через API
- ✅ Обработка callback'ов от Platega
- ✅ Проверка статуса платежа
- ✅ Заглушки для X-MerchantId и X-Secret
- ✅ Добавлен промокод FRIEND15

### v1.0.0
- Базовая функциональность покупки VPN
- 5 тарифных планов
- Система промокодов
- История заказов

## 🆘 Troubleshooting

**Ошибка "Payment gateway timeout"**
- Проверьте доступность API Platega.io
- Увеличьте timeout в настройках

**Заказы не создаются**
- Проверьте права на запись в data.json
- Убедитесь, что пользователь авторизован

**Platega.io возвращает ошибку**
- Проверьте правильность MerchantId и SecretKey
- Убедитесь, что ваш аккаунт Platega активен

## 📞 Поддержка

При возникновении проблем проверьте логи приложения:
```python
logger.info("Platega.io callback received: order=..., status=...")
```
