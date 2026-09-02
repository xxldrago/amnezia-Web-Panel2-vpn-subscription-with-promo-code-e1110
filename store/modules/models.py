"""SQLAlchemy-модели модулей store (заказы, рефералы, тикеты, настройки)."""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from store.app import db


class VpnPurchase(db.Model):
    """Заказ VPN-подписки."""
    __tablename__ = 'vpn_purchases'

    id = Column(Integer, primary_key=True)
    order_id = Column(String(100), unique=True, index=True)
    user_id = Column(String(64), index=True, nullable=False)  # user_id панели (uuid)
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
    status = Column(String(20), default='pending', index=True)

    # Даты
    created_at = Column(DateTime, default=datetime.utcnow)
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
    is_trial = Column(Boolean, default=False)

    # Выданные подключения (конфиги/ссылки) — JSON для гибкости
    issued_connections = Column(JSON, default=list)

    def as_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'user_id': self.user_id,
            'username': self.username,
            'plan_id': self.plan_id,
            'plan_label': self.plan_label,
            'days': self.days,
            'base_price': self.base_price,
            'discount': self.discount,
            'discount_percent': self.discount_percent,
            'promocode': self.promocode,
            'final_price': self.final_price,
            'payment_method': self.payment_method,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'paid_at': self.paid_at.isoformat() if self.paid_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'provisioned': self.provisioned,
            'provisioned_at': self.provisioned_at.isoformat() if self.provisioned_at else None,
            'is_trial': self.is_trial,
            'issued_connections': self.issued_connections or [],
        }

    def __repr__(self):
        return f"<VpnPurchase {self.order_id} {self.status}>"


class ReferralUser(db.Model):
    """Пользователь реферальной системы (обвязка по user_id панели)."""
    __tablename__ = 'referral_users'

    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), unique=True, index=True, nullable=False)
    username = Column(String(100))
    referral_code = Column(String(16), unique=True, index=True)
    referred_by = Column(String(64), nullable=True)
    first_deposit_made = Column(Boolean, default=False)
    total_bonus_received = Column(Float, default=0)


class ReferralTransaction(db.Model):
    """Транзакции реферальных бонусов."""
    __tablename__ = 'referral_transactions'

    id = Column(Integer, primary_key=True)
    referrer_id = Column(String(64), index=True)
    referred_user_id = Column(String(64))
    transaction_type = Column(String(32))  # first_deposit_bonus / commission
    amount = Column(Float)
    deposit_amount = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class Ticket(db.Model):
    """Тикет поддержки."""
    __tablename__ = 'support_tickets'

    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    username = Column(String(100))
    subject = Column(String(200))
    status = Column(String(20), default='open', index=True)  # open / answered / closed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TicketMessage(db.Model):
    """Сообщение в тикете."""
    __tablename__ = 'ticket_messages'

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey('support_tickets.id'))
    author_role = Column(String(20))  # user / admin / bot
    author_id = Column(String(64))
    body = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship('Ticket', backref='messages')


class Setting(db.Model):
    """Централизованное хранилище настроек (ключ-значение)."""
    __tablename__ = 'store_settings'

    key = Column(String(100), primary_key=True)
    value = Column(Text, default='')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TrialSubscription(db.Model):
    """Активированные тестовые подписки (один раз на пользователя)."""
    __tablename__ = 'trial_subscriptions'

    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), unique=True, index=True, nullable=False)
    order_id = Column(String(100))
    activated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    days = Column(Integer, default=3)