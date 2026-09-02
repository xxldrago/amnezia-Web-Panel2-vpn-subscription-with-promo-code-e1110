"""Реферальная система store (Flask).

- Пользователь панели получает реферальный код и ссылку /store/referral.
- При первом заходе авторизованного юзера с cookie ref=CODE создаётся связь (без хука в панель).
- on_user_deposit: первое пополнение (>min) даёт бонусы, последующие - комиссию пригласившему.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, render_template, make_response, redirect, url_for

from store.app import db
from store.modules.models import ReferralUser, ReferralTransaction
from store.modules import settings_manager as sm

logger = logging.getLogger(__name__)

referral_bp = Blueprint('referral', __name__, url_prefix='/store/referral')

CODE_REF_COOKIE = 'ref'
REF_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 дней


# ------------------------------------------------------------------
# Вспомогательные
# ------------------------------------------------------------------

def _user_from_panel():
    from store.panel_session import get_panel_user_id
    from store.panel_data import get_panel_user
    uid = get_panel_user_id(request.cookies.get('session', ''))
    if not uid:
        return None
    u = get_panel_user(uid)
    return {'user_id': uid, 'username': u.get('username', '') if u else ''}


def _generate_code() -> str:
    raw = uuid.uuid4().hex
    return hashlib.sha256(raw.encode()).hexdigest()[:8].upper()


def ensure_referral_user(user_id: str, username: str) -> ReferralUser:
    ru = ReferralUser.query.filter_by(user_id=user_id).first()
    if not ru:
        ru = ReferralUser(user_id=user_id, username=username, referral_code=_generate_code())
        db.session.add(ru)
        db.session.commit()
    return ru


def apply_referral_cookie(user_id: str, ref_code: str):
    """Привязывает пользователя к пригласившему по коду из cookie, если связи ещё нет."""
    ref_code = ref_code.strip()
    inviter = ReferralUser.query.filter_by(referral_code=ref_code.upper()).first()
    if not inviter or inviter.user_id == user_id:
        return
    ru = ReferralUser.query.filter_by(user_id=user_id).first()
    if ru is None:
        # Создаём запись реферала без кода привязки ещё кого-то
        ru = ReferralUser(user_id=user_id, referral_code=_generate_code(), referred_by=inviter.user_id)
        db.session.add(ru)
        db.session.commit()
        logger.info(f"Реферал {user_id} привязан к {inviter.user_id}")


def on_user_deposit(user_id: str, username: str, amount: float) -> dict:
    """Обработка пополнения: начисление бонусов пригласившему."""
    if amount <= 0:
        return {'success': False, 'error': 'Некорректная сумма'}

    cfg = sm.get_referral_cfg()
    min_deposit = cfg.get('min_deposit_for_bonus', 100)
    new_bonus = cfg.get('bonus_new_user', 100)
    inviter_first = cfg.get('bonus_inviter_first', 100)
    commission = cfg.get('commission_percent', 0.25)

    ru = ensure_referral_user(user_id, username)
    bonus_amount = 0
    bonus_type = None

    if ru.referred_by:
        if not ru.first_deposit_made and amount >= min_deposit:
            # Первое пополнение: бонус рефералу + вознаграждение пригласившему
            ru.first_deposit_made = True
            bonus_amount = new_bonus
            bonus_type = 'first_deposit_bonus'
            ru.total_bonus_received += bonus_amount

            inviter = ReferralUser.query.filter_by(user_id=ru.referred_by).first()
            if inviter:
                inviter.total_bonus_received += inviter_first
                db.session.add(ReferralTransaction(
                    referrer_id=inviter.user_id,
                    referred_user_id=user_id,
                    transaction_type='first_deposit_bonus',
                    amount=inviter_first,
                    deposit_amount=amount,
                ))
                bonus_amount = new_bonus
                bonus_type = 'first_deposit_bonus'
        elif ru.first_deposit_made:
            # Последующие пополнения: комиссия пригласившему
            com = round(amount * commission, 2)
            inviter = ReferralUser.query.filter_by(user_id=ru.referred_by).first()
            if inviter:
                inviter.total_bonus_received += com
                db.session.add(ReferralTransaction(
                    referrer_id=inviter.user_id,
                    referred_user_id=user_id,
                    transaction_type='commission',
                    amount=com,
                    deposit_amount=amount,
                ))
                bonus_amount = com
                bonus_type = 'commission'

    db.session.commit()
    return {'success': True, 'bonus_amount': bonus_amount, 'bonus_type': bonus_type}


# ------------------------------------------------------------------
# Страницы и API
# ------------------------------------------------------------------

@referral_bp.route('')
def referral_page():
    user = _user_from_panel()
    if not user:
        return redirect(url_for('vpn_purchase.purchase_page'))

    # Лениво применяем реф-код из cookie и гарантируем код пользователя
    ref = request.cookies.get(CODE_REF_COOKIE, '')
    if ref:
        apply_referral_cookie(user['user_id'], ref)
    ru = ensure_referral_user(user['user_id'], user['username'])

    site_url = sm.get_site_url()
    share_url = f"{site_url}/store/referral?invite={ru.referral_code}"

    # Статистика
    referred = ReferralUser.query.filter_by(referred_by=user['user_id']).count()
    first_dep = ReferralUser.query.filter_by(referred_by=user['user_id'], first_deposit_made=True).count()
    earned = ReferralTransaction.query.filter_by(referrer_id=user['user_id']).all()
    total_earned = sum(t.amount for t in earned) if earned else 0

    stats = {
        'invited': referred,
        'first_deposit': first_dep,
        'total_earned': round(total_earned, 2),
    }
    return render_template('referral.html', code=ru.referral_code, share_url=share_url, stats=stats)


@referral_bp.route('/landing')
def landing():
    """Точка входа по реферальной ссылке: сохраняет код в cookie и шлёт на покупку."""
    invite = request.args.get('invite')
    resp = make_response(redirect(url_for('vpn_purchase.purchase_page')))
    if invite:
        resp.set_cookie(CODE_REF_COOKIE, invite, max_age=REF_COOKIE_MAX_AGE, httponly=True, samesite='Lax')
    return resp


@referral_bp.route('/api/stats')
def api_stats():
    user = _user_from_panel()
    if not user:
        return jsonify({'error': 'Не авторизован'}), 401
    ru = ensure_referral_user(user['user_id'], user['username'])
    referred = ReferralUser.query.filter_by(referred_by=user['user_id']).count()
    total_earned = sum(t.amount for t in ReferralTransaction.query.filter_by(referrer_id=user['user_id']).all())
    return jsonify({
        'code': ru.referral_code,
        'referred': referred,
        'total_earned': round(total_earned, 2),
    })


def setup_referral(app):
    app.register_blueprint(referral_bp)
    logger.info("Referral system: настроена")