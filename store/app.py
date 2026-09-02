"""
Flask-система store: покупка VPN, реферальная система, тикеты, настройки.

Работает как отдельный контейнер (порт 5150), вложенный к Amnezia Web Panel.
Использует общую Starlette-cookie сессию панели и общий data.json.
Данные модулей (заказы, рефералы, тикеты) хранятся в PostgreSQL.
"""
import logging
import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("store")

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)

    # === Настройки из окружения ===
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-prod')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'STORE_DATABASE_URI',
        'postgresql://storeuser:storepass@db:5432/storedb'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JSON_AS_ASCII'] = False

    # Параметры панели (для авто-выдачи через её API)
    app.config['PANEL_API_BASE'] = os.environ.get('PANEL_API_BASE', 'http://panel:5000')
    app.config['PANEL_API_TOKEN'] = os.environ.get('PANEL_API_TOKEN', '')
    app.config['SITE_URL'] = os.environ.get('SITE_URL', 'http://panel.3set.online')

    db.init_app(app)

    with app.app_context():
        from store.modules.settings_manager import setup_settings
        from store.modules.referral_system import setup_referral
        from store.modules.vpn_purchase import setup_purchase
        from store.modules.support_tickets import setup_tickets
        from store.modules.auth import setup_auth

        # Создаём таблицы (модели регистрируются при импорте модулей)
        db.create_all()

        # Регистрация blueprint'ов
        setup_settings(app)
        setup_referral(app)
        setup_purchase(app)
        setup_tickets(app)
        setup_auth(app)

        logger.info("Store: все модули инициализированы")

    @app.route('/store/health')
    def health():
        return {'status': 'ok'}

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5150')))