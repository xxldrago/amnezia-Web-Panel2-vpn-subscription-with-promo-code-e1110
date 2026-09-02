"""Централизованный менеджер настроек (тарифы, платёжки, промокоды, бот, SMTP).

Все модули читают настройки из единого хранилища (таблица Setting), а не из кода.
Админ меняет их "на лету" через API/admins, без перезагрузки приложения.
"""
import json
import logging
import os

from flask import Blueprint, request, jsonify, render_template, redirect, url_for

from store.app import db
from store.modules.models import Setting

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings_manager', __name__, url_prefix='/store/api/settings')

# Значения по умолчанию (если в БД не задано)
DEFAULTS = {
    'site_name': 'Amnezia Panel',
    'site_url': os.environ.get('SITE_URL', 'http://panel.3set.online'),
    'admin_email': '',
    # Платёжная система
    'platega_merchant_id': os.environ.get('PLATEGA_MERCHANT_ID', ''),
    'platega_secret_key': os.environ.get('PLATEGA_SECRET_KEY', ''),
    # Тарифы
    'pricing': {
        '15_days': {"days": 15, "price": 200, "label": "15 дней"},
        '1_month': {"days": 30, "price": 400, "label": "1 месяц"},
        '3_months': {"days": 90, "price": 1100, "label": "3 месяца"},
        '6_months': {"days": 180, "price": 2100, "label": "6 месяцев"},
        '12_months': {"days": 365, "price": 4000, "label": "12 месяцев"},
    },
    # Промокоды
    'promo_codes': {
        'WELCOME10': {"discount_percent": 10, "uses_limit": 100, "uses_count": 0},
        'NEWUSER20': {"discount_percent": 20, "uses_limit": 50, "uses_count": 0},
    },
    # Реферальная система
    'referral': {
        'bonus_new_user': 100,
        'bonus_inviter_first': 100,
        'commission_percent': 0.25,
        'min_deposit_for_bonus': 100,
    },
    # Telegram-бот
    'telegram_token': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
    'telegram_admin_ids': '',
    # SMTP / Email
    'smtp_server': os.environ.get('SMTP_SERVER', ''),
    'smtp_port': int(os.environ.get('SMTP_PORT', '587')),
    'smtp_user': os.environ.get('SMTP_USER', ''),
    'smtp_password': os.environ.get('SMTP_PASSWORD', ''),
    'smtp_from': os.environ.get('SMTP_FROM', ''),
}


def _get_value(key, default=None):
    row = db.session.get(Setting, key)
    if row is None:
        return default
    return row.value


def _set_value(key, value):
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=json.dumps(value, ensure_ascii=False))
        db.session.add(row)
    else:
        row.value = json.dumps(value, ensure_ascii=False)


def load_all_settings(memo=None) -> dict:
    """Возвращает объединённый словарь настроек (defaults + сохранённые)."""
    result = json.loads(json.dumps(DEFAULTS))
    for row in db.session.query(Setting).all():
        key = row.key
        try:
            value = json.loads(row.value)
        except (ValueError, TypeError):
            value = row.value
        result[key] = value
    return result


def save_settings(data: dict):
    for key, value in data.items():
        _set_value(key, value)
    db.session.commit()


def get_pricing() -> dict:
    s = load_all_settings()
    return s.get('pricing', DEFAULTS['pricing'])


def get_promo_codes() -> dict:
    s = load_all_settings()
    return s.get('promo_codes', DEFAULTS['promo_codes'])


def get_referral_cfg() -> dict:
    s = load_all_settings()
    return s.get('referral', DEFAULTS['referral'])


def get_site_url() -> str:
    return load_all_settings().get('site_url', DEFAULTS['site_url'])


def get_admin_email() -> str:
    return load_all_settings().get('admin_email', '')


@settings_bp.route('', methods=['GET'])
def api_get_settings():
    return jsonify(load_all_settings())


@settings_bp.route('', methods=['POST'])
def api_save_settings():
    payload = request.get_json(force=True)
    save_settings(payload)
    return jsonify({'status': 'success', 'settings': load_all_settings()})


def setup_settings(app):
    app.register_blueprint(settings_bp)
    logger.info("Settings manager: настроен")