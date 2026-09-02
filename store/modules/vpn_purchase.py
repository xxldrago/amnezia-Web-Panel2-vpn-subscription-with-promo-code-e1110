"""Flask-модуль покупки VPN подписок (Platega.io).

Заменяет FastAPI-версию vpn_purchase.py и работает внутри store-сервиса.
Заказы хранятся в PostgreSQL (модель VpnPurchase).
После оплаты запускает авто-выдачу через API панели (vpn_provision).
"""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

import httpx
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session

from store.app import db
from store.modules.models import VpnPurchase
from store.modules import vpn_provision
from store.modules import settings_manager as sm

logger = logging.getLogger(__name__)

purchase_bp = Blueprint('vpn_purchase', __name__, url_prefix='/store/vpn')

PLATEGA_API_CREATE = 'https://app.platega.io/api/v1/payment-link/create'


# ------------------------------------------------------------------
# Helpers (платёжный шлюз, промокоды, тарифы)
# ------------------------------------------------------------------

def _platega_headers():
    s = sm.load_all_settings()
    merchant = s.get('platega_merchant_id', '')
    secret = s.get('platega_secret_key', '')
    return {
        'Content-Type': 'application/json',
        'X-MerchantId': merchant,
        'X-Secret': secret,
    }


def _creds_configured() -> bool:
    s = sm.load_all_settings()
    return bool(s.get('platega_merchant_id') and s.get('platega_secret_key'))


def create_payment_link(order: dict) -> dict:
    """Создаёт платёжную ссылку Platega.io; в симуляции возвращает фиктивную."""
    if not _creds_configured():
        logger.warning("Platega credentials не настроены — режим симуляции")
        return {
            'success': True,
            'payment_url': f"https://app.platega.io/pay?order={order.get('order_id')}&amount={order.get('amount')}",
            'order_id': order.get('order_id'),
            'simulated': True,
        }

    site_url = sm.get_site_url()
    payload = {
        'amount': order['amount'],
        'currency': 'RUB',
        'orderId': order['order_id'],
        'description': f"VPN Subscription: {order['plan_label']}",
        'successUrl': f"{site_url}/store/vpn/payment/success?order_id={order['order_id']}",
        'failUrl': f"{site_url}/store/vpn/payment/fail?order_id={order['order_id']}",
        'customer': {
            'email': order.get('email', ''),
            'name': order.get('username', ''),
        },
    }
    try:
        resp = httpx.post(PLATEGA_API_CREATE, json=payload, headers=_platega_headers(), timeout=30)
        data = resp.json()
        if resp.status_code == 200 and data.get('url'):
            return {'success': True, 'payment_url': data['url'], 'order_id': order['order_id']}
        logger.error(f"Platega create error: {resp.status_code} {data}")
        return {'success': False, 'error': 'Ошибка создания платежа', 'detail': data}
    except Exception as e:
        logger.exception("Platega exception")
        return {'success': False, 'error': str(e)}


def _apply_promo(plan_price: float, promo_code: str) -> tuple:
    """Возвращает (final_price, discount, discount_percent) или скидка 0."""
    promos = sm.get_promo_codes()
    p = promos.get(promo_code.upper())
    if not p:
        return plan_price, 0, 0
    percent = p.get('discount_percent', 0)
    discount = round(plan_price * percent / 100, 2)
    return round(plan_price - discount, 2), discount, percent


def _user_from_panel():
    """Возвращает dict {user_id, username} из сессии панели."""
    from store.panel_session import get_panel_user_id
    from store.panel_data import get_panel_user
    uid = get_panel_user_id(request.cookies.get('session', ''))
    if not uid:
        return None
    u = get_panel_user(uid)
    return {'user_id': uid, 'username': u.get('username', '') if u else ''}


# ------------------------------------------------------------------
# Страницы и API
# ------------------------------------------------------------------

@purchase_bp.route('/purchase')
def purchase_page():
    pricing = sm.get_pricing()
    user = _user_from_panel()
    return render_template('vpn_purchase.html', pricing=pricing, user=user)


@purchase_bp.route('/calculate', methods=['POST'])
def calculate():
    body = request.get_json(force=True)
    plan_id = body.get('plan_id')
    promo = body.get('promocode', '')
    pricing = sm.get_pricing()
    plan = pricing.get(plan_id)
    if not plan:
        return jsonify({'error': 'Неверный тариф'}), 400
    final_price, discount, percent = _apply_promo(plan['price'], promo)
    return jsonify({
        'plan_id': plan_id,
        'price': plan['price'],
        'discount': discount,
        'discount_percent': percent,
        'final_price': final_price,
        'promocode': promo.upper() if promo else None,
    })


@purchase_bp.route('/create_order', methods=['POST'])
def create_order():
    user = _user_from_panel()
    if not user:
        return jsonify({'error': 'Вы не авторизованы'}), 401

    body = request.get_json(force=True)
    plan_id = body.get('plan_id')
    promo = body.get('promocode', '')
    pricing = sm.get_pricing()
    plan = pricing.get(plan_id)
    if not plan:
        return jsonify({'error': 'Неверный тариф'}), 400

    plan_price = plan['price']
    final_price, discount, percent = _apply_promo(plan_price, promo)
    now = datetime.utcnow()
    order_id = f"VPN_{user['username']}_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:4]}"

    order = VpnPurchase(
        order_id=order_id,
        user_id=user['user_id'],
        username=user['username'],
        plan_id=plan_id,
        plan_label=plan['label'],
        days=plan['days'],
        base_price=plan_price,
        discount=discount,
        discount_percent=percent,
        promocode=promo.upper() if promo else None,
        final_price=final_price,
        payment_method='platega',
        payment_method_name='Platega.io',
        status='pending',
        created_at=now,
        expires_at=now + timedelta(days=plan['days']),
    )
    db.session.add(order)
    db.session.commit()

    pay = create_payment_link({
        'order_id': order_id,
        'amount': final_price,
        'plan_label': plan['label'],
        'username': user['username'],
        'email': '',
    })
    if pay.get('payment_url'):
        order.payment_url = pay['payment_url']
        db.session.commit()

    return jsonify({
        'status': 'created',
        'order_id': order_id,
        'final_price': final_price,
        'payment_url': pay.get('payment_url'),
        'simulated': pay.get('simulated', False),
    })


@purchase_bp.route('/platega/callback', methods=['POST'])
def platega_callback():
    """Webhook от Platega.io: меняет статус заказа на paid и запускает авто-выдачу."""
    data = request.get_json(force=True, silent=True) or request.form.to_dict()
    transaction_id = data.get('transaction_id') or data.get('transactionId')
    order_id = data.get('order_id') or data.get('orderId')
    status = (data.get('status') or '').lower()

    order = VpnPurchase.query.filter_by(order_id=order_id).first()
    if not order:
        logger.warning(f"Callback для неизвестного заказа {order_id}")
        return jsonify({'status': 'error', 'message': 'unknown order'}), 404

    # Проверка подписи (если включена)
    if 'X-Platega-Signature' in request.headers:
        s = sm.load_all_settings()
        secret = s.get('platega_secret_key', '')
        if secret:
            signature = request.headers.get('X-Platega-Signature')
            body = request.get_data(as_text=True)
            expected = hmac.new(secret.encode(), json.dumps(json.loads(body), sort_keys=True).encode(), hashlib.sha256).hexdigest()
            if signature != expected:
                return jsonify({'status': 'error', 'message': 'bad signature'}), 403

    if status in ('completed', 'paid', 'success'):
        if order.status != 'paid':
            order.status = 'paid'
            order.paid_at = datetime.utcnow()
            order.platega_transaction_id = transaction_id
            db.session.commit()
            logger.info(f"Заказ {order_id} оплачен, запускаю авто-выдачу")
            vpn_provision.provision_purchase(order)
            # Рефералка: начисляем бонусы по пополнению
            try:
                from store.modules.referral_system import on_user_deposit
                on_user_deposit(order.user_id, order.username, order.final_price)
            except Exception:
                logger.exception("Ошибка реферального начисления")
        return jsonify({'status': 'ok'})
    elif status in ('failed', 'cancelled', 'expired'):
        order.status = 'cancelled'
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'ignored'}), 200


@purchase_bp.route('/payment/success', methods=['GET'])
def payment_success():
    order_id = request.args.get('order_id')
    order = VpnPurchase.query.filter_by(order_id=order_id).first()
    return render_template('payment_result.html', success=True, order=order)


@purchase_bp.route('/payment/fail', methods=['GET'])
def payment_fail():
    order_id = request.args.get('order_id')
    order = VpnPurchase.query.filter_by(order_id=order_id).first()
    return render_template('payment_result.html', success=False, order=order)


@purchase_bp.route('/my-orders', methods=['GET'])
def my_orders():
    user = _user_from_panel()
    if not user:
        return jsonify({'error': 'Вы не авторизованы'}), 401
    orders = VpnPurchase.query.filter_by(user_id=user['user_id']).order_by(VpnPurchase.created_at.desc()).all()
    from store.modules.models import TrialSubscription
    trial_used = db.session.query(TrialSubscription).filter_by(user_id=user['user_id']).first() is not None
    return jsonify({
        'orders': [o.as_dict() for o in orders],
        'trial_used': trial_used,
        'trial_available': not trial_used,
    })


@purchase_bp.route('/activate_trial', methods=['POST'])
def activate_trial():
    user = _user_from_panel()
    if not user:
        return jsonify({'error': 'Вы не авторизованы'}), 401
    result = vpn_provision.activate_trial_and_provision(user['user_id'], user['username'])
    return jsonify(result)


def setup_purchase(app):
    app.register_blueprint(purchase_bp)
    logger.info("VPN Purchase module: настроен")