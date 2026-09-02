"""Авто-выдача доступов: создание VPN-подключений через API Amnezia Web Panel.

После успешной оплаты подписки (статус 'paid') модуль создаёт подключение
пользователю на всех серверах панели через её json API:
    POST /api/users/{user_id}/connections/add
Требуется Bearer-токен панели (awp_...) с ролью admin/support.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from store.app import db
from store.modules import settings_manager as sm
from store.modules.models import VpnPurchase, TrialSubscription

logger = logging.getLogger("vpn_provision")

# Карта длительности планов (в днях)
PLAN_DAYS = {
    '15_days': 15,
    '1_month': 30,
    '3_months': 90,
    '6_months': 180,
    '12_months': 365,
    'trial': 3,
}


def _api_base() -> str:
    from flask import current_app
    return current_app.config.get('PANEL_API_BASE', 'http://panel:5000')


def _api_token() -> str:
    from flask import current_app
    return current_app.config.get('PANEL_API_TOKEN', '')


def create_connection_on_server(user_id: str, server: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Создаёт подключение пользователю на конкретном сервере.

    server — объект из data.json (с полем 'protocols').
    Возвращает результат API или None при ошибке.
    """
    protocol = None
    # Ищем установленный протокол среди protocols сервера
    protocols = server.get('protocols', {})
    for proto_key, rec in protocols.items():
        if rec and rec.get('installed') and proto_key in ('awg', 'wireguard', 'xray', 'telemt', 'socks5'):
            protocol = proto_key
            break
    if not protocol:
        logger.info(f"Сервер {server.get('name')}: нет установленного VPN-протокола, пропуск")
        return None

    payload = {
        'server_id': server.get('_index', 0),
        'protocol': protocol,
        'name': f"VPN подключение",
    }
    url = f"{_api_base()}/api/users/{user_id}/connections/add"
    headers = {
        'Authorization': f"Bearer {_api_token()}",
        'Content-Type': 'application/json',
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"[{server.get('name')}] Подключение создано: {data}")
            return data
        else:
            logger.error(f"[{server.get('name')}] API вернул {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        logger.error(f"[{server.get('name')}] Ошибка вызова API: {e}")
        return None


def provision_purchase(purchase: VpnPurchase) -> bool:
    """Выдаёт доступы по оплаченному заказу, помечает provisioned."""
    from store.panel_data import get_panel_servers

    servers = get_panel_servers()
    success_count = 0
    issued = []
    for idx, srv in enumerate(servers):
        srv['_index'] = idx
        result = create_connection_on_server(purchase.user_id, srv)
        if result:
            success_count += 1
            issued.append({
                'server': srv.get('name'),
                'protocol': result.get('protocol'),
                'vpn_link': result.get('vpn_link'),
                'config': result.get('config'),
            })

    purchase.servers_count = len(servers)
    purchase.successful_connections = success_count
    purchase.provisioned = True
    purchase.provisioned_at = __import__('datetime').datetime.utcnow()
    purchase.issued_connections = issued
    db.session.add(purchase)
    db.session.commit()
    logger.info(f"Авто-выдача: {success_count}/{len(servers)} серверов, заказ {purchase.order_id}")
    return success_count > 0


def activate_trial_and_provision(user_id: str, username: str) -> Dict[str, Any]:
    """Активация тестовой подписки (3 дня) + авто-выдача."""
    from store.modules.settings_manager import get_pricing

    existing = TrialSubscription.query.filter_by(user_id=user_id).first()
    if existing:
        return {'success': False, 'error': 'Вы уже использовали тестовую подписку'}

    days = 3
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    order_id = f"TRIAL_{user_id[:8]}_{now.strftime('%Y%m%d%H%M%S')}"
    purchase = VpnPurchase(
        order_id=order_id,
        user_id=user_id,
        username=username,
        plan_id='trial',
        plan_label='Тестовая подписка на все сервера',
        days=days,
        base_price=0,
        final_price=0,
        payment_method='trial',
        payment_method_name='Тестовый период',
        status='paid',
        is_trial=True,
        paid_at=now,
        expires_at=now + timedelta(days=days),
    )
    db.session.add(purchase)

    trial = TrialSubscription(
        user_id=user_id,
        order_id=order_id,
        activated_at=now,
        expires_at=now + timedelta(days=days),
        days=days,
    )
    db.session.add(trial)
    db.session.commit()

    provision_purchase(purchase)
    return {'success': True, 'order_id': order_id, 'days': days}