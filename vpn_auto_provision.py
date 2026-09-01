"""
VPN Auto-Provisioning Module
Независимый модуль для автоматического создания ключей доступа на всех серверах
после успешной оплаты подписки.

Работает через прослушивание событий БД или прямой вызов, не требуя изменения
основного кода приложения.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import event
from sqlalchemy.orm import Session

# Настройка логгирования
logger = logging.getLogger("vpn_auto_provision")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class ServerConnector:
    """
    Адаптер для взаимодействия с серверами.
    В методе _connect_to_server_api реализуйте логику подключения к вашей панели управления серверами.
    Это единственное место, которое может потребовать обновления при изменении API панели.
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session

    def get_all_active_servers(self) -> List[Any]:
        """
        Получает список всех активных серверов из БД.
        ЗАМЕНИТЕ 'Server' на вашу реальную модель сервера, если она отличается.
        Предполагается, что у модели есть поля: id, name, ip_address, api_port, status
        """
        try:
            # Импортируем модель внутри функции, чтобы избежать циклических импортов
            # Если ваша модель называется иначе, измените импорт ниже
            from app import Server 
            servers = self.db.query(Server).filter(Server.status == 'active').all()
            return servers
        except ImportError:
            logger.error("Модель Server не найдена. Проверьте импорт в ServerConnector.get_all_active_servers")
            return []
        except Exception as e:
            logger.error(f"Ошибка получения списка серверов: {e}")
            return []

    def create_user_on_server(self, server: Any, user_id: int, duration_days: int) -> Optional[Dict[str, Any]]:
        """
        Создает подключение для пользователя на конкретном сервере.
        
        Args:
            server: Объект сервера из БД
            user_id: ID пользователя
            duration_days: Срок действия в днях
            
        Returns:
            Dict с данными подключения (key, config_url и т.д.) или None при ошибке
        """
        try:
            # --- ЗДЕСЬ ВАША ЛОГИКА СОЗДАНИЯ КЛЮЧА НА СЕРВЕРЕ ---
            # Пример того, что должно происходить внутри:
            # 1. Отправить запрос на API сервера (WireGuard/XRay/Outline)
            # 2. Получить конфиг или ключ
            # 3. Сохранить данные в БД
            
            logger.info(f"Создание подключения для пользователя {user_id} на сервере {server.name} ({server.ip_address})")
            
            # ЗАГЛУШКА: Имитация успешного создания
            # В реальности здесь будет вызов вашего API панели управления
            connection_data = {
                "server_id": server.id,
                "server_name": server.name,
                "protocol": "wireguard", # или vless, shadowsocks
                "config_key": f"wg_key_{user_id}_{server.id}_{datetime.now().timestamp()}",
                "config_url": f"https://{server.ip_address}/config/{user_id}.conf",
                "expires_at": datetime.now() + timedelta(days=duration_days)
            }
            
            # Здесь можно сохранить connection_data в таблицу Connections вашей БД
            # self._save_connection_to_db(user_id, connection_data)
            
            return connection_data
            
        except Exception as e:
            logger.error(f"Не удалось создать подключение на сервере {server.name}: {e}")
            return None

    def _save_connection_to_db(self, user_id: int, connection_data: Dict[str, Any]):
        """Сохраняет данные подключения в БД."""
        # Реализуйте сохранение в вашу таблицу подключений
        pass


class AutoProvisioningService:
    """Сервис обработки успешных покупок и выдачи доступов."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.connector = ServerConnector(db_session)

    def provision_access(self, purchase_record: Any):
        """
        Основной метод: создает доступы на всех серверах после покупки.
        
        Args:
            purchase_record: Объект записи о покупке (из модуля vpn_purchase)
        """
        user_id = purchase_record.user_id
        duration_days = self._calculate_duration_days(purchase_record.plan_code)
        
        if duration_days <= 0:
            logger.error(f"Некорректный срок действия для плана {purchase_record.plan_code}")
            return False

        logger.info(f"Начало авто-выдачи доступа для пользователя {user_id}. План: {purchase_record.plan_code}, Срок: {duration_days} дн.")
        
        servers = self.connector.get_all_active_servers()
        
        if not servers:
            logger.warning("Активные серверы не найдены. Доступ не выдан.")
            return False

        successful_creations = 0
        failed_creations = 0
        
        for server in servers:
            result = self.connector.create_user_on_server(server, user_id, duration_days)
            if result:
                successful_creations += 1
                logger.info(f"Успешно создано подключение на сервере {server.name}")
            else:
                failed_creations += 1
                logger.error(f"Неудача при создании подключения на сервере {server.name}")

        # Обновляем статус заказа, если все успешно (или частично)
        if successful_creations > 0:
            self._mark_order_as_fulfilled(purchase_record, successful_creations, len(servers))
            return True
        else:
            logger.error(f"Не удалось создать ни одного подключения для заказа {purchase_record.id}")
            return False

    def _calculate_duration_days(self, plan_code: str) -> int:
        """Переводит код тарифа в дни."""
        mapping = {
            '15_days': 15,
            '1_month': 30,
            '3_months': 90,
            '6_months': 180,
            '12_months': 365,
            'trial': 3  # Тестовая подписка на 3 дня
        }
        return mapping.get(plan_code, 0)

    def _mark_order_as_fulfilled(self, purchase: Any, success_count: int, total_count: int):
        """Обновляет запись о заказе, фиксируя выдачу доступов."""
        try:
            purchase.provisioned = True
            purchase.provisioned_at = datetime.now()
            purchase.servers_count = total_count
            purchase.successful_connections = success_count
            # purchase.status = 'completed' # Если у вас есть такое поле
            
            # Для тестовых подписок также помечаем как выполненные
            if getattr(purchase, 'is_trial', False):
                logger.info(f"Тестовая подписка {purchase.id} успешно активирована")
            
            self.db.commit()
            logger.info(f"Заказ {purchase.id} помечен как выполненный ({success_count}/{total_count})")
        except Exception as e:
            logger.error(f"Ошибка обновления статуса заказа: {e}")
            self.db.rollback()


# --- ИНТЕГРАЦИЯ ЧЕРЕЗ СОБЫТИЯ SQLALCHEMY (РЕКОМЕНДУЕМЫЙ СПОСОБ) ---

def register_listeners(engine, purchase_model_class):
    """
    Регистрирует слушатели событий БД.
    Вызывается ОДИН РАЗ при старте приложения.
    
    Args:
        engine: SQLAlchemy engine вашего приложения
        purchase_model_class: Класс модели покупки (например, VpnPurchase из vpn_purchase.py)
    """
    
    @event.listens_for(purchase_model_class, 'after_update')
    def receive_after_update(mapper, connection, target):
        """
        Срабатывает при обновлении записи о покупке.
        Проверяет, сменился ли статус на 'paid' и не было ли выдано доступов ранее.
        """
        # Проверяем, что статус стал 'paid' (или 'success') и флаг provisioned еще False
        # Атрибуты могут отличаться в зависимости от вашей реализации в vpn_purchase.py
        current_status = getattr(target, 'status', None)
        is_provisioned = getattr(target, 'provisioned', False)
        
        # Предполагаем, что в модели есть статусы 'pending', 'paid', 'failed'
        if current_status == 'paid' and not is_provisioned:
            logger.info(f"Обнаружена новая успешная оплата (ID: {target.id}). Запуск выдачи доступов...")
            
            # Создаем новую сессию для безопасной работы
            session_cls = Session.object_session(target).__class__
            with session_cls(bind=connection) as session:
                # Получаем свежий объект, чтобы избежать проблем с детачем
                fresh_target = session.get(purchase_model_class, target.id)
                if fresh_target and fresh_target.status == 'paid' and not fresh_target.provisioned:
                    service = AutoProvisioningService(session)
                    try:
                        service.provision_access(fresh_target)
                    except Exception as e:
                        logger.critical(f"Критическая ошибка в процессе авто-выдачи: {e}")
                        session.rollback()
                    # Коммит делается внутри сервиса, но если нужно глобально - здесь

def setup_auto_provisioning(app, db_engine, purchase_model):
    """
    Точка входа для интеграции в приложение Flask/FastAPI.
    
    Usage в main app.py:
        from vpn_auto_provision import setup_auto_provisioning
        from vpn_purchase import VpnPurchase
        
        setup_auto_provisioning(app, db.engine, VpnPurchase)
    """
    logger.info("Инициализация модуля авто-выдачи VPN доступов...")
    register_listeners(db_engine, purchase_model)
    logger.info("Модуль авто-выдачи успешно активирован и слушает события БД.")
