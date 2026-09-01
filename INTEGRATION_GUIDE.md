# Полная инструкция по интеграции модулей VPN покупки и авто-выдачи

## 📦 Созданные файлы

1. **`vpn_purchase.py`** - Модуль покупки VPN подписок с интеграцией Platega.io
2. **`vpn_auto_provision.py`** - Модуль автоматической выдачи доступов на всех серверах
3. **`templates/vpn_purchase.html`** - Страница покупки (нужно создать)
4. **`VPN_PURCHASE_MODULE_README.md`** - Документация по модулю покупки
5. **`AUTO_PROVISION_README.md`** - Документация по модулю авто-выдачи

---

## 🔌 Шаг 1: Интеграция в приложение (app.py)

Откройте ваш главный файл `app.py` и добавьте следующий код **после инициализации приложения и базы данных**:

```python
# ============================================================
# ИНТЕГРАЦИЯ МОДУЛЕЙ VPN ПОКУПКИ И АВТО-ВЫДАЧИ
# ============================================================

from vpn_purchase import setup_vpn_purchase_module
from vpn_auto_provision import setup_auto_provisioning
from vpn_purchase import VpnPurchase  # Или используйте модель из БД если она в SQLAlchemy

# 1. Подключаем модуль покупки VPN
setup_vpn_purchase_module(app)
logger.info("✅ Модуль покупки VPN подключен")

# 2. Подключаем модуль авто-выдачи доступов
# Важно: вызывайте ПОСЛЕ инициализации db.engine
try:
    # Если вы используете SQLAlchemy модель VpnPurchase
    # from models import VpnPurchase  # Импортируйте вашу реальную модель
    # setup_auto_provisioning(app, db.engine, VpnPurchase)
    
    # Если вы используете JSON-based хранение (как в текущей реализации),
    # модуль всё равно будет работать через события обновления записей
    logger.info("⚠️ Модуль авто-выдачи требует SQLAlchemy модель для полной интеграции")
    logger.info("📝 Для активации создайте модель VpnPurchase в SQLAlchemy и раскомментируйте код выше")
except Exception as e:
    logger.warning(f"Модуль авто-выдачи не активирован: {e}")
```

---

## 🗄️ Шаг 2: Создание SQLAlchemy модели (ОПЦИОНАЛЬНО, но РЕКОМЕНДУЕТСЯ)

Для полноценной работы авто-выдачи через события БД создайте модель:

```python
# В файле models.py или там где у вас другие модели
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from datetime import datetime

class VpnPurchase(Base):
    __tablename__ = 'vpn_purchases'
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(100), unique=True, index=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(100))
    plan_id = Column(String(50))
    plan_label = Column(String(50))
    days = Column(Integer)
    base_price = Column(Float)
    discount = Column(Float, default=0)
    discount_percent = Column(Integer, default=0)
    promocode = Column(String(50))
    final_price = Column(Float)
    payment_method = Column(String(50))
    payment_method_name = Column(String(100))
    
    # Статусы: pending, paid, active, expired, cancelled
    status = Column(String(20), default='pending')
    
    # Даты
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime)
    paid_at = Column(DateTime)
    
    # Platega.io данные
    payment_url = Column(String(500))
    platega_transaction_id = Column(String(100))
    
    # Авто-выдача доступов
    provisioned = Column(Boolean, default=False)
    provisioned_at = Column(DateTime)
    servers_count = Column(Integer, default=0)
    successful_connections = Column(Integer, default=0)
    connection_id = Column(String(100))
```

После создания модели обновите интеграцию в `app.py`:

```python
from models import VpnPurchase  # Ваша новая модель

setup_auto_provisioning(app, db.engine, VpnPurchase)
logger.info("✅ Модуль авто-выдачи активирован с SQLAlchemy моделью")
```

---

## 🎨 Шаг 3: Добавление ссылки в личный кабинет

Откройте файл шаблона личного кабинета (обычно `templates/my_connections.html` или `templates/cabinet.html`) и добавьте кнопку:

```html
<!-- Добавьте в раздел меню или действий -->
<div class="vpn-purchase-section">
    <h3>💙 Купить VPN подписку</h3>
    <p>Выберите удобный тарифный план и оплатите подписку</p>
    <a href="/vpn/purchase" class="btn btn-primary">
        🛒 Купить VPN
    </a>
</div>
```

Или в виде карточки:

```html
<div class="card">
    <div class="card-body">
        <h5 class="card-title">🔐 Нужен VPN?</h5>
        <p class="card-text">
            Тарифы от 200₽ до 4000₽.<br>
            Автоматическая выдача на всех серверах.
        </p>
        <a href="/vpn/purchase" class="btn btn-success">Купить подписку</a>
    </div>
</div>
```

---

## ⚙️ Шаг 4: Настройка Platega.io

### 4.1 Получите credentials в кабинете Platega.io
1. Зарегистрируйтесь на https://app.platega.io/
2. Создайте магазин/проект
3. Получите:
   - **Merchant ID** (идентификатор мерчанта)
   - **Secret Key** (секретный ключ API)

### 4.2 Настройте переменные окружения

**Linux/Mac:**
```bash
export PLATEGA_MERCHANT_ID='ваш_merchant_id'
export PLATEGA_SECRET_KEY='ваш_secret_key'
```

**Windows (PowerShell):**
```powershell
$env:PLATEGA_MERCHANT_ID='ваш_merchant_id'
$env:PLATEGA_SECRET_KEY='ваш_secret_key'
```

**Или в .env файл:**
```env
PLATEGA_MERCHANT_ID=your_merchant_id_here
PLATEGA_SECRET_KEY=your_secret_key_here
```

### 4.3 Настройте Webhook URL в Platega.io

В кабинете Platega.io укажите URL для уведомлений:
```
https://ваш-домен.ru/vpn/platega/callback
```

---

## 🖥️ Шаг 5: Настройка авто-выдачи на серверах

Откройте `vpn_auto_provision.py` и найдите класс `ServerConnector`. Отредактируйте методы:

### 5.1 Метод получения серверов
```python
def get_all_active_servers(self) -> List[Any]:
    try:
        from app import Server  # Замените на вашу модель
        servers = self.db.query(Server).filter(Server.status == 'active').all()
        return servers
    except ImportError:
        logger.error("Модель Server не найдена")
        return []
```

### 5.2 Метод создания подключения (САМОЕ ВАЖНОЕ!)
```python
def create_user_on_server(self, server: Any, user_id: int, duration_days: int):
    try:
        logger.info(f"Создание подключения для пользователя {user_id} на сервере {server.name}")
        
        # --- ВСТАВЬТЕ СЮДА ВАШ КОД ---
        # Пример для WireGuard API:
        import requests
        
        response = requests.post(
            f"http://{server.ip_address}:{server.api_port}/api/users",
            json={
                "user_id": user_id,
                "duration_days": duration_days
            },
            headers={"Authorization": f"Bearer {server.api_token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                "server_id": server.id,
                "server_name": server.name,
                "protocol": "wireguard",
                "config_key": data['key'],
                "config_url": data['config_url'],
                "expires_at": datetime.now() + timedelta(days=duration_days)
            }
        else:
            logger.error(f"Ошибка API сервера: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка создания подключения: {e}")
        return None
```

---

## 🧪 Шаг 6: Тестирование

### 6.1 Проверка импорта модулей
```bash
cd /workspace
python -c "import vpn_purchase; import vpn_auto_provision; print('✅ Модули загружены')"
```

### 6.2 Тестовая покупка (в режиме симуляции)
1. Запустите приложение
2. Перейдите на `/vpn/purchase`
3. Выберите тариф (например, 15 дней - 200₽)
4. Введите промокод `WELCOME10` (скидка 10%)
5. Нажмите "Купить"
6. Так как credentials не настроены, откроется симуляция оплаты

### 6.3 Проверка логов
```bash
tail -f logs/app.log | grep -E "(vpn_purchase|vpn_auto_provision)"
```

---

## 📊 Архитектура работы

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│ Пользователь│────▶│ Форма покупки│────▶│ Создание заказа │
└─────────────┘     └──────────────┘     └─────────────────┘
                                              │
                                              ▼
                                       ┌──────────────┐
                                       │ Platega.io   │
                                       │ (оплата)     │
                                       └──────────────┘
                                              │
                         ┌────────────────────┼────────────────────┐
                         │                    │                    │
                         ▼                    ▼                    ▼
                  ┌─────────────┐    ┌─────────────┐    ┌──────────────┐
                  │ Webhook     │    │ Success URL │    │ Fail URL     │
                  │ /callback   │    │ /success    │    │ /fail        │
                  └─────────────┘    └─────────────┘    └──────────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │ Статус      │
                  │ заказа →    │
                  │ 'paid'      │
                  └─────────────┘
                         │
          ╔══════════════╧══════════════╗
          ║  СОБЫТИЕ БД (after_update)  ║
          ╚══════════════╤══════════════╝
                         ▼
                  ┌─────────────────────┐
                  │ AutoProvisioning    │
                  │ Service             │
                  └─────────────────────┘
                         │
                         ▼
                  ┌─────────────────────┐
                  │ Получить все        │
                  │ активные серверы    │
                  └─────────────────────┘
                         │
                         ▼
                  ┌─────────────────────┐
                  │ Для каждого сервера:│
                  │ • Создать ключ      │
                  │ • Сохранить конфиг  │
                  └─────────────────────┘
                         │
                         ▼
                  ┌─────────────────────┐
                  │ Пометить заказ как  │
                  │ выполненный         │
                  └─────────────────────┘
```

---

## 🔧 Troubleshooting

### Ошибка: "Модель Server не найдена"
**Решение:** Проверьте имя вашей модели сервера и обновите импорт в `vpn_auto_provision.py`:
```python
from app import VpnServer  # или другое имя
```

### Ошибка: "Platega.io credentials are not configured"
**Решение:** Установите переменные окружения или замените заглушки в `vpn_purchase.py`:
```python
PLATEGA_MERCHANT_ID = 'real_merchant_id'
PLATEGA_SECRET_KEY = 'real_secret_key'
```

### Авто-выдача не срабатывает
**Решение:** 
1. Убедитесь, что модель `VpnPurchase` создана в SQLAlchemy
2. Проверьте, что `setup_auto_provisioning()` вызывается после `db.engine`
3. Посмотрите логи на предмет ошибок

### Промокоды не работают
**Решение:** Проверьте константу `PROMO_CODES` в `vpn_purchase.py`:
```python
PROMO_CODES = {
    "WELCOME10": {"discount_percent": 10, "uses_limit": 100, "uses_count": 0},
    "NEWUSER20": {"discount_percent": 20, "uses_limit": 50, "uses_count": 0},
}
```

---

## 📝 Чек-лист перед запуском

- [ ] Переменные окружения Platega.io установлены
- [ ] Модель `VpnPurchase` создана (для SQLAlchemy)
- [ ] `setup_vpn_purchase_module(app)` добавлен в `app.py`
- [ ] `setup_auto_provisioning(...)` добавлен в `app.py`
- [ ] Ссылка на `/vpn/purchase` добавлена в личный кабинет
- [ ] Метод `create_user_on_server` настроен под вашу инфраструктуру
- [ ] Webhook URL настроен в кабинете Platega.io
- [ ] Тестовая покупка прошла успешно

---

## 🆘 Поддержка

При возникновении проблем:
1. Проверьте логи приложения
2. Убедитесь, что все зависимости установлены (`pip install sqlalchemy httpx`)
3. Проверьте документацию Platega.io: https://docs.platega.io/
