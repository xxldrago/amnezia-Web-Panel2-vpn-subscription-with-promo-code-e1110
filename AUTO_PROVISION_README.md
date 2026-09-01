# Модуль авто-выдачи VPN доступов (Auto-Provisioning)

## Описание
Этот модуль автоматически создает ключи доступа (конфигурации) на **всех активных серверах** вашей панели сразу после успешной оплаты подписки пользователем.

### Ключевые особенности
- **Полная независимость**: Работает через прослушивание событий базы данных (SQLAlchemy Events). Не требует изменения контроллеров или роутов основного приложения.
- **Отказоустойчивость**: При обновлении основного кода модуль продолжит работать, так как опирается только на структуру БД и события ORM.
- **Масштабируемость**: Автоматически обнаруживает все активные серверы в системе и выдает доступ на каждом из них.
- **Логирование**: Подробный лог всех операций для отладки.

---

## Как это работает
1. Пользователь оплачивает подписку через форму покупки.
2. Платежная система (Platega.io) отправляет Webhook, статус заказа в БД меняется на `paid`.
3. **Модуль `vpn_auto_provision.py` перехватывает это изменение** через событие `after_update`.
4. Запускается процесс `AutoProvisioningService`:
   - Получает список всех серверов со статусом `active`.
   - Для каждого сервера вызывает метод создания подключения.
   - Сохраняет результаты (ключи, конфиги) в БД.
   - Помечает заказ как выполненный (`provisioned = True`).

---

## Интеграция

### 1. Подключение в приложении
В вашем главном файле запуска (например, `app.py` или `main.py`), после инициализации базы данных, добавьте всего две строки:

```python
from vpn_auto_provision import setup_auto_provisioning
from vpn_purchase import VpnPurchase  # Импорт модели покупки из модуля оплаты

# ... инициализация app и db ...

# Активация модуля авто-выдачи
setup_auto_provisioning(app, db.engine, VpnPurchase)
```

### 2. Настройка работы с серверами
Откройте файл `vpn_auto_provision.py` и найдите класс `ServerConnector`. Вам нужно адаптировать два метода под вашу инфраструктуру:

#### А. Получение списка серверов
Метод `get_all_active_servers`:
```python
def get_all_active_servers(self) -> List[Any]:
    try:
        from app import Server  # Убедитесь, что импорт соответствует вашему проекту
        servers = self.db.query(Server).filter(Server.status == 'active').all()
        return servers
    except ImportError:
        # Обработка ошибки, если модель называется иначе
        return []
```
*Если ваша модель сервера называется иначе (например, `VpnServer`), замените импорт.*

#### Б. Создание подключения на сервере
Метод `create_user_on_server` — это место, где происходит магия. Сейчас там стоит заглушка. Вам нужно вставить реальный вызов API вашей панели управления (WireGuard, XRay, Outline и т.д.).

```python
def create_user_on_server(self, server: Any, user_id: int, duration_days: int) -> Optional[Dict[str, Any]]:
    try:
        logger.info(f"Создание подключения для пользователя {user_id} на сервере {server.name}")
        
        # --- ВСТАВЬТЕ СЮДА ВАШ КОД ВЫЗОВА API СЕРВЕРА ---
        # Пример (псевдокод):
        # response = requests.post(
        #     f"http://{server.ip_address}:{server.api_port}/api/users",
        #     json={"user_id": user_id, "duration": duration_days},
        #     headers={"Authorization": f"Bearer {server.api_token}"}
        # )
        # data = response.json()
        
        connection_data = {
            "server_id": server.id,
            "server_name": server.name,
            "protocol": "wireguard",
            "config_key": "real_key_from_api", 
            "config_url": f"https://{server.ip_address}/s/{user_id}",
            "expires_at": datetime.now() + timedelta(days=duration_days)
        }
        
        # Сохранение в БД (реализуйте метод _save_connection_to_db)
        self._save_connection_to_db(user_id, connection_data)
        
        return connection_data
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return None
```

---

## Структура данных
Модуль ожидает, что в модели покупки (`VpnPurchase`) появятся следующие поля (добавьте их в `vpn_purchase.py`, если их нет):
- `provisioned` (Boolean): Флаг, выданы ли уже доступы.
- `provisioned_at` (DateTime): Время выдачи.
- `servers_count` (Integer): Сколько всего серверов было доступно.
- `successful_connections` (Integer): На скольких серверах удалось создать ключ.

## Логирование
Все логи выводятся в консоль с тегом `vpn_auto_provision`. Рекомендуется настроить сохранение логов в файл для аудита:
```python
import logging
logger = logging.getLogger("vpn_auto_provision")
handler = logging.FileHandler('vpn_provision.log')
logger.addHandler(handler)
```
