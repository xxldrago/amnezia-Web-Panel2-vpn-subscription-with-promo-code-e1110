# 🎁 Интеграция реферальной системы - Пошаговое руководство

## 📦 Созданные файлы

1. **`referral_system.py`** (478 строк) - Основной модуль реферальной системы
2. **`templates/referral.html`** (574 строки) - Страница реферальной программы с красивым UI
3. **`REFERRAL_SYSTEM_README.md`** - Полная документация
4. **`REFERRAL_INTEGRATION_GUIDE.md`** - Это руководство по интеграции

---

## ⚡ Быстрая интеграция (6 шагов)

### Шаг 1: Импортировать модуль в app.py

Добавьте в начало `app.py`:

```python
from referral_system import setup_referral_system, on_user_register, on_user_deposit
```

### Шаг 2: Инициализировать систему

После создания `app = Flask(__name__)` добавьте:

```python
# Инициализация реферальной системы
setup_referral_system(app)

# Укажите базовый URL вашего сайта
app.config['BASE_URL'] = 'https://yoursite.com'  # Замените на ваш домен
```

### Шаг 3: Добавить роут для страницы рефералов

```python
@app.route('/referral')
@login_required  # Используйте ваш декоратор авторизации
def referral_page():
    return render_template('referral.html')
```

### Шаг 4: Интегрировать с регистрацией

Найдите вашу функцию регистрации и добавьте вызов после создания пользователя:

**Было:**
```python
@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    
    new_user = User(username=username, email=email, password=password)
    db.session.add(new_user)
    db.session.commit()
    
    return redirect(url_for('dashboard'))
```

**Стало:**
```python
@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    
    new_user = User(username=username, email=email, password=password)
    db.session.add(new_user)
    db.session.commit()
    
    # === ДОБАВИТЬ ЭТО ===
    user_id = str(new_user.id)  # Преобразуйте ID в строку
    on_user_register(user_id)
    # ====================
    
    return redirect(url_for('dashboard'))
```

### Шаг 5: Интегрировать с пополнением счета

Найдите обработчик успешного платежа и добавьте вызов:

**Было:**
```python
@app.route('/deposit/success')
def deposit_success():
    user_id = current_user.id
    amount = float(request.args.get('amount'))
    
    # Обновляем баланс пользователя
    current_user.balance += amount
    db.session.commit()
    
    return redirect(url_for('dashboard'))
```

**Стало:**
```python
@app.route('/deposit/success')
def deposit_success():
    user_id = current_user.id
    amount = float(request.args.get('amount'))
    
    # Обновляем баланс пользователя
    current_user.balance += amount
    db.session.commit()
    
    # === ДОБАВИТЬ ЭТО ===
    result = on_user_deposit(str(user_id), amount)
    
    if result.get('success') and result.get('bonus_amount', 0) > 0:
        flash(f"🎁 Реферальный бонус: {result['bonus_amount']}₽ начислен!", "success")
    # ====================
    
    return redirect(url_for('dashboard'))
```

### Шаг 6: Добавить ссылку в личный кабинет

Откройте ваш шаблон личного кабинета (например, `my_connections.html`, `dashboard.html`, `profile.html`) и добавьте ссылку:

```html
<!-- В меню или боковую панель -->
<div class="menu">
    <a href="{{ url_for('dashboard') }}" class="menu-item">
        🏠 Личный кабинет
    </a>
    <a href="{{ url_for('vpn_purchase') }}" class="menu-item">
        🔒 Купить VPN
    </a>
    <!-- === ДОБАВИТЬ ЭТО === -->
    <a href="{{ url_for('referral_page') }}" class="menu-item">
        🎁 Реферальная программа
    </a>
    <!-- ==================== -->
    <a href="{{ url_for('logout') }}" class="menu-item">
        🚪 Выйти
    </a>
</div>
```

---

## 🎯 Как это работает

### 1. Пользователь переходит по реферальной ссылке
```
https://yoursite.com/register?ref=ABC12345
```

### 2. Система автоматически сохраняет код
- Код сохраняется в сессию через `before_request` хук
- Cookie устанавливается на 30 дней

### 3. Новый пользователь регистрируется
- Вызывается `on_user_register(user_id)`
- Система проверяет сессию/cookie на наличие реферального кода
- Если код найден - пользователь привязывается к рефералу

### 4. Первое пополнение от 100₽
- Вызывается `on_user_deposit(user_id, amount)`
- Новый пользователь получает **100₽** бонуса
- Пригласивший получает **100₽** бонуса
- Статистика обновляется

### 5. Повторные пополнения
- Пригласивший получает **25%** от суммы пополнения
- Пример: пополнение 500₽ → бонус 125₽

---

## 📊 Что видит пользователь

### Страница `/referral` отображает:

1. **Персональный реферальный код** (8 символов, например `A1B2C3D4`)
2. **Реферальная ссылка** для копирования и шеринга
3. **Кнопки действий**:
   - 📋 Копировать код
   - 🔗 Копировать ссылку
   - 📤 Поделиться (Web Share API на мобильных)

4. **Статистика** (6 карточек):
   - 👥 Приглашено пользователей
   - 💳 Сделали первое пополнение
   - ✅ Активных рефералов
   - 📈 Конверсия %
   - 💰 Заработано всего ₽
   - 📅 За последний месяц ₽

5. **Информация о бонусах**:
   - Новый пользователь: 100₽ при первом пополнении от 100₽
   - Ваш бонус за первого реферала: 100₽
   - Комиссия с последующих пополнений: 25%

---

## 🔧 Настройка параметров

Откройте `referral_system.py` и измените константы в начале файла:

```python
REFERRAL_BONUS_NEW_USER = 100        # Бонус новому пользователю (₽)
REFERRAL_BONUS_INVITER_FIRST = 100   # Бонус пригласившему за первое пополнение (₽)
REFERRAL_COMMISSION_PERCENT = 0.25   # Комиссия (25% = 0.25)
MIN_DEPOSIT_FOR_BONUS = 100          # Минимальное пополнение для бонуса (₽)
```

---

## 🗄️ Хранение данных

Модуль создает собственную базу данных для независимости:

```
workspace/
├── referral_system.py          # Модуль
├── data/
│   └── referral_system.db      # База данных рефералов
├── templates/
│   └── referral.html           # Страница реферальной программы
└── REFERRAL_*.md               # Документация
```

### Таблицы БД:

1. **referral_users**
   - `user_id` - ID пользователя из основной системы
   - `referral_code` - Уникальный код (8 символов)
   - `referred_by` - Кто пригласил (user_id)
   - `first_deposit_made` - Было ли первое пополнение (0/1)
   - `total_bonus_received` - Всего получено бонусов

2. **referral_transactions**
   - `referrer_id` - Кто получил бонус
   - `referred_user_id` - Кого пригласили
   - `transaction_type` - 'first_deposit_bonus' или 'commission'
   - `amount` - Сумма бонуса
   - `deposit_amount` - Сумма пополнения

3. **referral_stats_cache**
   - Кэш статистики для быстрого доступа
   - Обновляется автоматически

---

## 🧪 Тестирование

### Проверка работы:

1. **Создайте тестового пользователя A**
   - Зайдите в `/referral`
   - Скопируйте реферальный код (например `ABCD1234`)

2. **Создайте тестового пользователя B**
   - Откройте инкогнито окно
   - Перейдите по ссылке: `https://yoursite.com/register?ref=ABCD1234`
   - Зарегистрируйтесь

3. **Проверьте привязку**
   - В базе `referral_system.db` у пользователя B должно быть `referred_by = user_id_A`

4. **Сделайте первое пополнение**
   - Пополните счет пользователя B на 200₽
   - Проверьте что:
     - Пользователь B получил 100₽ бонуса
     - Пользователь A получил 100₽ бонуса
     - Статистика обновилась

5. **Сделайте повторное пополнение**
   - Пополните счет пользователя B еще на 500₽
   - Проверьте что пользователь A получил 125₽ (500 * 25%)

---

## 🔐 Безопасность

- ✅ Уникальные коды через SHA-256
- ✅ Защита от повторной привязки
- ✅ HttpOnly cookie
- ✅ SameSite=Lax защита
- ✅ Валидация сумм пополнения
- ✅ Проверка существования реферала

---

## 📱 Мобильная версия

Страница полностью адаптивна:
- Desktop: 6 колонок статистики в ряд
- Tablet: 2 колонки
- Mobile: 1 колонка с крупными элементами
- Поддержка Web Share API для нативного шеринга

---

## 🚨 Возможные проблемы и решения

### Проблема: Реферальный код не применяется

**Решение:**
```python
# Проверьте что before_request хук работает
print(session.get('referral_code'))  # Должен показать код

# Проверьте базу данных
import sqlite3
conn = sqlite3.connect('data/referral_system.db')
cursor = conn.cursor()
cursor.execute("SELECT * FROM referral_users")
print(cursor.fetchall())
```

### Проблема: Бонусы не начисляются

**Решение:**
```python
# Убедитесь что on_user_deposit вызывается ПОСЛЕ успешного платежа
# Проверьте логи
import logging
logging.basicConfig(level=logging.INFO)

# Проверьте сумму пополнения
if amount < 100:
    print("Слишком маленькая сумма для бонуса")
```

### Проблема: Статистика не обновляется

**Решение:**
```python
# Проверьте права на запись в БД
import os
os.chmod('data/referral_system.db', 0o666)

# Проверьте API endpoint
curl http://localhost:5000/api/referral/stats \
  -H "Cookie: session=..."
```

---

## 📈 Масштабирование

Для больших проектов:

1. **Заменить SQLite на PostgreSQL**
```python
engine = create_engine('postgresql://user:pass@localhost/referrals')
```

2. **Добавить Redis кэш**
```python
import redis
r = redis.Redis(host='localhost', port=6379)
r.setex(f'stats:{user_id}', 300, json.dumps(stats))
```

3. **Асинхронная обработка через Celery**
```python
@celery.task
def process_referral_bonus(user_id, amount):
    on_user_deposit(user_id, amount)
```

---

## ✅ Чеклист интеграции

- [ ] Импортирован модуль в `app.py`
- [ ] Вызван `setup_referral_system(app)`
- [ ] Установлен `BASE_URL`
- [ ] Добавлен роут `/referral`
- [ ] Интегрировано с регистрацией (`on_user_register`)
- [ ] Интегрировано с пополнением (`on_user_deposit`)
- [ ] Добавлена ссылка в личный кабинет
- [ ] Протестирована реферальная ссылка
- [ ] Протестированы бонусы
- [ ] Проверена статистика

---

## 🎉 Готово!

Теперь у вас есть полноценная реферальная система которая:
- ✅ Работает независимо от основного кода
- ✅ Продолжит работать при обновлениях
- ✅ Имеет красивый адаптивный интерфейс
- ✅ Автоматически начисляет бонусы
- ✅ Показывает детальную статистику

**Документация:**
- `REFERRAL_SYSTEM_README.md` - Полная документация API
- `referral_system.py` - Исходный код с комментариями
