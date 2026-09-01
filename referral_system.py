"""
Независимый модуль реферальной системы для VPN сервиса.
Работает автономно, не требует изменений в основных моделях пользователя.
Хранит данные в отдельной БД/файле для устойчивости к обновлениям основного кода.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, session, redirect, url_for, current_app
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import hashlib

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
REFERRAL_BONUS_NEW_USER = 100  # Бонус новому пользователю
REFERRAL_BONUS_INVITER_FIRST = 100  # Бонус пригласившему за первое пополнение реферала
REFERRAL_COMMISSION_PERCENT = 0.25  # 25% комиссия с последующих пополнений
MIN_DEPOSIT_FOR_BONUS = 100  # Минимальное пополнение для активации бонуса

# Путь к файлу хранения данных (для устойчивости)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
REFERRAL_DB_PATH = os.path.join(DATA_DIR, 'referral_system.db')

# Создаем директорию если нет
os.makedirs(DATA_DIR, exist_ok=True)

# SQLAlchemy setup
engine = create_engine(f'sqlite:///{REFERRAL_DB_PATH}', echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

# === Модели данных ===

class ReferralUser(Base):
    """Таблица пользователей реферальной системы"""
    __tablename__ = 'referral_users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), unique=True, nullable=False, index=True)  # ID пользователя из основной системы
    referral_code = Column(String(50), unique=True, nullable=False, index=True)
    referred_by = Column(String(255), nullable=True, index=True)  # Кто пригласил (user_id)
    registered_at = Column(DateTime, default=datetime.utcnow)
    first_deposit_made = Column(Integer, default=0)  # Было ли первое пополнение (0/1)
    total_bonus_received = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferralTransaction(Base):
    """Таблица транзакций реферальной системы"""
    __tablename__ = 'referral_transactions'
    
    id = Column(Integer, primary_key=True)
    referrer_id = Column(String(255), nullable=False, index=True)  # Кто получил бонус
    referred_user_id = Column(String(255), nullable=False, index=True)  # Кого пригласили
    transaction_type = Column(String(50), nullable=False)  # 'first_deposit_bonus', 'commission'
    amount = Column(Float, nullable=False)
    deposit_amount = Column(Float, nullable=False)  # Сумма пополнения, с которой начислено
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferralStatsCache(Base):
    """Кэш статистики для быстрого доступа"""
    __tablename__ = 'referral_stats_cache'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), unique=True, nullable=False, index=True)
    total_invited = Column(Integer, default=0)
    first_deposit_count = Column(Integer, default=0)
    active_referrals_count = Column(Integer, default=0)
    total_earned = Column(Float, default=0.0)
    month_earned = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Инициализация базы данных"""
    Base.metadata.create_all(engine)
    logger.info("Реферальная БД инициализирована")


def get_session():
    """Получение сессии БД"""
    return SessionLocal()


def generate_referral_code(user_id):
    """Генерация уникального реферального кода"""
    hash_input = f"{user_id}{uuid.uuid4().hex}{datetime.utcnow().isoformat()}"
    code = hashlib.sha256(hash_input.encode()).hexdigest()[:8].upper()
    return code


def get_or_create_referral_user(user_id, referral_code_from_session=None):
    """Получить или создать запись пользователя в реферальной системе"""
    session = get_session()
    try:
        user = session.query(ReferralUser).filter_by(user_id=user_id).first()
        if not user:
            code = generate_referral_code(user_id)
            user = ReferralUser(
                user_id=user_id,
                referral_code=code,
                referred_by=referral_code_from_session
            )
            session.add(user)
            session.commit()
            logger.info(f"Создан реферальный пользователь {user_id} с кодом {code}")
        
        # Возвращаем данные как dict чтобы избежать DetachedInstanceError
        return {
            'id': user.id,
            'user_id': user.user_id,
            'referral_code': user.referral_code,
            'referred_by': user.referred_by,
            'registered_at': user.registered_at,
            'first_deposit_made': user.first_deposit_made,
            'total_bonus_received': user.total_bonus_received
        }
    finally:
        session.close()


def set_referral_cookie(response, referral_code):
    """Установка cookie с реферальным кодом"""
    response.set_cookie(
        'referral_code',
        referral_code,
        max_age=30*24*60*60,  # 30 дней
        httponly=True,
        samesite='Lax'
    )
    return response


def check_referral_from_cookie():
    """Проверка реферального кода из cookie"""
    return request.cookies.get('referral_code')


def apply_referral_to_new_user(user_id, referral_code=None):
    """Привязка нового пользователя к рефералу"""
    if not referral_code:
        referral_code = check_referral_from_cookie()
    
    if not referral_code:
        return False
    
    session = get_session()
    try:
        # Проверяем существует ли такой реферальный код
        referrer = session.query(ReferralUser).filter_by(referral_code=referral_code).first()
        if not referrer:
            return False
        
        # Проверяем не привязан ли уже пользователь
        user = session.query(ReferralUser).filter_by(user_id=user_id).first()
        if user and user.referred_by:
            return False  # Уже привязан
        
        # Привязываем
        if not user:
            user = ReferralUser(
                user_id=user_id,
                referral_code=generate_referral_code(user_id),
                referred_by=referrer.user_id
            )
            session.add(user)
        else:
            user.referred_by = referrer.user_id
        
        session.commit()
        logger.info(f"Пользователь {user_id} привязан к рефералу {referrer.user_id}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка привязки реферала: {e}")
        return False
    finally:
        session.close()


def process_deposit(user_id, amount):
    """
    Обработка пополнения счета пользователя для начисления реферальных бонусов.
    Вызывать после успешного пополнения в основной системе.
    """
    session = get_session()
    try:
        user = session.query(ReferralUser).filter_by(user_id=user_id).first()
        if not user or not user.referred_by:
            return {"success": False, "message": "Нет реферала"}
        
        referrer = session.query(ReferralUser).filter_by(user_id=user.referred_by).first()
        if not referrer:
            return {"success": False, "message": "Реферал не найден"}
        
        bonus_amount = 0
        transaction_type = ""
        
        # Первое пополнение
        if not user.first_deposit_made and amount >= MIN_DEPOSIT_FOR_BONUS:
            # Бонус новому пользователю
            user.total_bonus_received += REFERRAL_BONUS_NEW_USER
            # Бонус пригласившему
            referrer.total_bonus_received += REFERRAL_BONUS_INVITER_FIRST
            
            bonus_amount = REFERRAL_BONUS_INVITER_FIRST
            transaction_type = 'first_deposit_bonus'
            
            user.first_deposit_made = 1
            
            logger.info(f"Первое пополнение: {user_id} получил {REFERRAL_BONUS_NEW_USER}₽, {referrer.user_id} получил {REFERRAL_BONUS_INVITER_FIRST}₽")
        
        # Последующие пополнения - комиссия 25%
        elif user.first_deposit_made:
            commission = amount * REFERRAL_COMMISSION_PERCENT
            if commission > 0:
                referrer.total_bonus_received += commission
                bonus_amount = commission
                transaction_type = 'commission'
                
                logger.info(f"Комиссия с пополнения: {referrer.user_id} получил {commission:.2f}₽ ({amount}₽ * 25%)")
        
        # Записываем транзакцию если был бонус
        if bonus_amount > 0:
            transaction = ReferralTransaction(
                referrer_id=referrer.user_id,
                referred_user_id=user.user_id,
                transaction_type=transaction_type,
                amount=bonus_amount,
                deposit_amount=amount
            )
            session.add(transaction)
        
        # Обновляем кэш статистики
        update_stats_cache(referrer.user_id)
        
        session.commit()
        return {
            "success": True,
            "bonus_amount": bonus_amount,
            "new_balance": referrer.total_bonus_received
        }
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка обработки депозита: {e}")
        return {"success": False, "message": str(e)}
    finally:
        session.close()


def update_stats_cache(user_id):
    """Обновление кэша статистики для пользователя"""
    session = get_session()
    try:
        # Подсчет статистики
        total_invited = session.query(ReferralUser).filter_by(referred_by=user_id).count()
        
        first_deposit_count = session.query(ReferralUser).filter_by(
            referred_by=user_id,
            first_deposit_made=1
        ).count()
        
        # Активные рефералы (те у кого было первое пополнение)
        active_referrals_count = first_deposit_count
        
        # Всего заработано
        total_earned = session.query(func.sum(ReferralTransaction.amount)).filter_by(
            referrer_id=user_id
        ).scalar() or 0.0
        
        # Заработано за последний месяц
        month_ago = datetime.utcnow() - timedelta(days=30)
        month_earned = session.query(func.sum(ReferralTransaction.amount)).filter(
            ReferralTransaction.referrer_id == user_id,
            ReferralTransaction.created_at >= month_ago
        ).scalar() or 0.0
        
        # Конверсия
        conversion = (first_deposit_count / total_invited * 100) if total_invited > 0 else 0
        
        # Сохраняем в кэш
        stats = session.query(ReferralStatsCache).filter_by(user_id=user_id).first()
        if not stats:
            stats = ReferralStatsCache(user_id=user_id)
            session.add(stats)
        
        stats.total_invited = total_invited
        stats.first_deposit_count = first_deposit_count
        stats.active_referrals_count = active_referrals_count
        stats.total_earned = total_earned
        stats.month_earned = month_earned
        stats.last_updated = datetime.utcnow()
        
        session.commit()
        
        return {
            "total_invited": total_invited,
            "first_deposit_count": first_deposit_count,
            "active_referrals_count": active_referrals_count,
            "conversion": round(conversion, 2),
            "total_earned": total_earned,
            "month_earned": month_earned
        }
    except Exception as e:
        logger.error(f"Ошибка обновления статистики: {e}")
        return None
    finally:
        session.close()


def get_user_stats(user_id):
    """Получение статистики пользователя"""
    session = get_session()
    try:
        stats = session.query(ReferralStatsCache).filter_by(user_id=user_id).first()
        if not stats:
            # Если кэша нет, обновляем
            return update_stats_cache(user_id)
        
        # Пересчитываем конверсию
        conversion = (stats.active_referrals_count / stats.total_invited * 100) if stats.total_invited > 0 else 0
        
        return {
            "total_invited": stats.total_invited,
            "first_deposit_count": stats.first_deposit_count,
            "active_referrals_count": stats.active_referrals_count,
            "conversion": round(conversion, 2),
            "total_earned": stats.total_earned,
            "month_earned": stats.month_earned,
            "last_updated": stats.last_updated.isoformat() if stats.last_updated else None
        }
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return None
    finally:
        session.close()


def get_referral_info(user_id):
    """Получение полной информации о реферальной системе для пользователя"""
    session = get_session()
    try:
        user = session.query(ReferralUser).filter_by(user_id=user_id).first()
        if not user:
            user = get_or_create_referral_user(user_id)
        
        stats = get_user_stats(user_id)
        
        # Формируем ссылку (базовый URL берем из конфига или ставим заглушку)
        base_url = current_app.config.get('BASE_URL', 'https://yoursite.com') if current_app else 'https://yoursite.com'
        referral_link = f"{base_url}/register?ref={user.referral_code}"
        
        return {
            "referral_code": user.referral_code,
            "referral_link": referral_link,
            "referred_by": user.referred_by,
            "stats": stats,
            "bonus_info": {
                "new_user_bonus": REFERRAL_BONUS_NEW_USER,
                "inviter_first_bonus": REFERRAL_BONUS_INVITER_FIRST,
                "commission_percent": int(REFERRAL_COMMISSION_PERCENT * 100),
                "min_deposit": MIN_DEPOSIT_FOR_BONUS
            }
        }
    except Exception as e:
        logger.error(f"Ошибка получения реферальной информации: {e}")
        return None
    finally:
        session.close()


# === Flask Blueprint ===

referral_bp = Blueprint('referral', __name__, url_prefix='/api/referral')


@referral_bp.route('/info', methods=['GET'])
def api_get_info():
    """API: Получить реферальную информацию текущего пользователя"""
    # Предполагаем что user_id хранится в сессии или токене
    user_id = session.get('user_id') or request.headers.get('X-User-ID')
    
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 401
    
    info = get_referral_info(user_id)
    if info:
        return jsonify(info)
    return jsonify({"error": "Failed to get referral info"}), 500


@referral_bp.route('/process_deposit', methods=['POST'])
def api_process_deposit():
    """API: Обработать пополнение для начисления реферальных бонусов"""
    data = request.json
    user_id = data.get('user_id') or session.get('user_id')
    amount = float(data.get('amount', 0))
    
    if not user_id or amount <= 0:
        return jsonify({"error": "Invalid data"}), 400
    
    result = process_deposit(user_id, amount)
    return jsonify(result)


@referral_bp.route('/stats', methods=['GET'])
def api_get_stats():
    """API: Получить статистику текущего пользователя"""
    user_id = session.get('user_id') or request.headers.get('X-User-ID')
    
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 401
    
    stats = get_user_stats(user_id)
    if stats:
        return jsonify(stats)
    return jsonify({"error": "Failed to get stats"}), 500


@referral_bp.route('/apply', methods=['POST'])
def api_apply_referral():
    """API: Применить реферальный код при регистрации"""
    data = request.json
    user_id = data.get('user_id')
    referral_code = data.get('referral_code')
    
    if not user_id or not referral_code:
        return jsonify({"error": "Invalid data"}), 400
    
    success = apply_referral_to_new_user(user_id, referral_code)
    if success:
        return jsonify({"success": True, "message": "Referral applied"})
    return jsonify({"success": False, "message": "Failed to apply referral"}), 400


def setup_referral_system(app):
    """
    Инициализация реферальной системы.
    Вызвать в main app.py после создания app.
    """
    init_db()
    app.register_blueprint(referral_bp)
    
    @app.before_request
    def before_request_referral():
        """Сохранение реферального кода из URL в сессию при регистрации"""
        if request.endpoint and 'register' in request.endpoint:
            ref_code = request.args.get('ref')
            if ref_code:
                session['referral_code'] = ref_code
    
    logger.info("Реферальная система инициализирована")


# === Хелперы для интеграции ===

def on_user_register(user_id, referral_code=None):
    """
    Вызвать после регистрации нового пользователя.
    Автоматически применит реферальный код из cookie/session.
    """
    apply_referral_to_new_user(user_id, referral_code)
    get_or_create_referral_user(user_id, referral_code)


def on_user_deposit(user_id, amount):
    """
    Вызвать после успешного пополнения счета пользователя.
    Начислит реферальные бонусы если есть реферал.
    """
    return process_deposit(user_id, amount)


if __name__ == '__main__':
    # Тестирование
    init_db()
    print("Реферальная система готова к работе")
