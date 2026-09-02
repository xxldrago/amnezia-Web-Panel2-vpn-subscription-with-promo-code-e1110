"""Flask-модуль аутентификации store: вход, регистрация, восстановление пароля, вход через Telegram.

Панельные пользователи живут в data.json панели (store монтирует его read-only).
Поэтому store:
  - при регистрации создаёт панельного юзера через панельный API POST /api/users/add (токен),
  - при входе вызывает панельный POST /api/auth/login и пробрасывает cookie `session`,
  - при входе через Telegram сам генерирует валидную cookie-сессию (общий SECRET_KEY),
  - при восстановлении пароля шлёт одноразовый код через Telegram-бота и меняет пароль через API.
"""
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

import httpx
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, make_response, current_app

from store.app import db
from store.modules.models import LoginCode
from store.panel_data import get_panel_users, get_panel_user

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/store/auth')

CODE_TTL_MINUTES = 15


# ------------------------------------------------------------------
# Панельные вызовы (API с токеном)
# ------------------------------------------------------------------

def _panel_base():
    return current_app.config.get('PANEL_API_BASE', 'http://panel:5000')


def _panel_token():
    return current_app.config.get('PANEL_API_TOKEN', '')


def _panel_headers():
    return {'Authorization': f"Bearer {_panel_token()}", 'Content-Type': 'application/json'}


def create_panel_user(username: str, password: str, email: str = '',
                      telegram_id: str = '') -> dict:
    """Создаёт пользователя панели через её API (роль user). Возвращает user_id или ошибку."""
    payload = {
        'username': username,
        'password': password,
        'role': 'user',
        'email': email,
        'telegramId': telegram_id,
    }
    resp = httpx.post(f"{_panel_base()}/api/users/add", json=payload,
                      headers=_panel_headers(), timeout=30)
    data = resp.json()
    if resp.status_code == 200 and data.get('status') == 'success':
        return {'success': True, 'user_id': data.get('user_id')}
    error = (data or {}).get('error', f"Панель вернула {resp.status_code}")
    return {'success': False, 'error': error}


def panel_login(username: str, password: str) -> tuple:
    """Вход в панель. Возвращает (success, session_cookie, role, error)."""
    resp = httpx.post(f"{_panel_base()}/api/auth/login",
                      json={'username': username, 'password': password}, timeout=30)
    data = resp.json() or {}
    if resp.status_code == 200 and data.get('status') == 'success':
        cookie = resp.headers.get('set-cookie', '')
        # Извлекаем значение cookie session=...
        session_val = ''
        for part in cookie.split(';'):
            part = part.strip()
            if part.startswith('session='):
                session_val = part[len('session='):]
                break
        return True, session_val, data.get('role'), ''
    return False, '', '', data.get('error', 'Неверный логин или пароль')


def update_panel_user_password(user_id: str, new_password: str) -> dict:
    """Меняет пароль панельного юзера через API."""
    resp = httpx.post(f"{_panel_base()}/api/users/{user_id}/update",
                      json={'password': new_password}, headers=_panel_headers(), timeout=30)
    data = resp.json() or {}
    if resp.status_code == 200:
        return {'success': True}
    return {'success': False, 'error': data.get('error', 'Ошибка смены пароля')}


def update_panel_user_telegram(user_id: str, telegram_id: str) -> dict:
    """Привязывает telegramId к панельному юзеру через API."""
    resp = httpx.post(f"{_panel_base()}/api/users/{user_id}/update",
                      json={'telegramId': telegram_id}, headers=_panel_headers(), timeout=30)
    data = resp.json() or {}
    if resp.status_code == 200:
        return {'success': True}
    return {'success': False, 'error': data.get('error', 'Ошибка привязки Telegram')}


# ------------------------------------------------------------------
# Коды (одноразовые) + Telegram-уведомление
# ------------------------------------------------------------------

def _gen_code() -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(6))


def generate_tg_code(telegram_id: str, code_type: str = 'tg_login', user_id: str = '') -> str:
    """Формирует одноразовый код (для бота) и сохраняет его в БД. Возвращает код."""
    with db.session.begin():
        # Инвалидируем старые неиспользованные коды аналогичного типа для telegram_id
        LoginCode.query.filter_by(telegram_id=telegram_id, code_type=code_type, used=False).update({'used': True})
        code = LoginCode(user_id=user_id, telegram_id=telegram_id, code=_gen_code(), code_type=code_type)
        db.session.add(code)
    return code.code


def _create_code(user_id: str, code_type: str = 'reset') -> LoginCode:
    # Инвалидируем старые неиспользованные коды для этого юзера этого типа
    LoginCode.query.filter_by(user_id=user_id, code_type=code_type, used=False).update({'used': True})
    code = LoginCode(user_id=user_id, code=_gen_code(), code_type=code_type)
    db.session.add(code)
    db.session.commit()
    return code


def _send_telegram(user_id: str, text: str) -> bool:
    """Отправляет сообщение пользователю через Telegram Bot API по его telegramId.

    Возвращает True, если отправлено успешно (или юзер был найден и попытка сделана).
    """
    import os
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    user = get_panel_user(user_id)
    if not token or not user:
        return False
    tg_id = str(user.get('telegramId', ''))
    if not tg_id:
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={'chat_id': tg_id, 'text': text},
            timeout=30,
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def _verify_code(user_id: str, code: str, code_type: str = 'reset') -> bool:
    entry = (LoginCode.query.filter_by(user_id=user_id, code=code, code_type=code_type, used=False)
             .order_by(LoginCode.id.desc()).first())
    if not entry:
        return False
    if entry.created_at < datetime.utcnow() - timedelta(minutes=CODE_TTL_MINUTES):
        return False
    entry.used = True
    db.session.commit()
    return True


def _user_from_cookie():
    from store.panel_session import get_panel_user_id
    uid = get_panel_user_id(request.cookies.get('session', ''))
    if not uid:
        return None
    u = get_panel_user(uid)
    return {'user_id': uid, 'username': u.get('username', '') if u else ''}


# ------------------------------------------------------------------
# Страницы
# ------------------------------------------------------------------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        user = _user_from_cookie()
        return render_template('auth_login.html', user=user, flash='', error='')

    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    if not username or not password:
        return render_template('auth_login.html', user=None, error='Введите логин и пароль', flash=''), 400

    ok, session_cookie, role, err = panel_login(username, password)
    if not ok:
        return render_template('auth_login.html', user=None, error=err or 'Неверный логин или пароль', flash=''), 401

    resp = make_response(redirect(url_for('vpn_purchase.purchase_page')))
    # Ставим ту же cookie-сессию, которую выдала панель (общий канал авторизации)
    if session_cookie:
        resp.set_cookie('session', session_cookie, max_age=60 * 60 * 24 * 14,
                        samesite='Lax', httponly=False, path='/')
    return resp


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('auth_register.html', error='', flash='', invite='')

    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    password2 = request.form.get('password2') or ''
    email = (request.form.get('email') or '').strip()
    invite = (request.form.get('invite') or '').strip()

    if len(username) < 3:
        return render_template('auth_register.html', error='Логин слишком короткий (мин. 3 символа)', flash='', invite=invite), 400
    if len(password) < 6:
        return render_template('auth_register.html', error='Пароль слишком короткий (мин. 6 символов)', flash='', invite=invite), 400
    if password != password2:
        return render_template('auth_register.html', error='Пароли не совпадают', flash='', invite=invite), 400

    res = create_panel_user(username, password, email, '')
    if not res['success']:
        msg = ('Пользователь с таким логином уже существует' if 'user_exists' in str(res.get('error'))
               else res.get('error', 'Ошибка регистрации'))
        return render_template('auth_register.html', error=msg, flash='', invite=invite), 400

    # Реферальная привязка
    try:
        from store.modules.referral_system import apply_referral_cookie
        from store.modules.referral_system import ensure_referral_user
        ensure_referral_user(res['user_id'], username)
        if invite:
            apply_referral_cookie(res['user_id'], invite)
    except Exception:
        logger.exception("Ошибка реферальной привязки при регистрации")

    # Автоматический вход через панельный логин
    ok, session_cookie, role, err = panel_login(username, password)
    if ok and session_cookie:
        resp = make_response(redirect(url_for('auth.tg_bind_prompt')))
        resp.set_cookie('session', session_cookie, max_age=60 * 60 * 24 * 14,
                        samesite='Lax', httponly=False, path='/')
        return resp

    return redirect(url_for('auth.login'))


@auth_bp.route('/bind', methods=['GET'])
def tg_bind_prompt():
    user = _user_from_cookie()
    if not user:
        return redirect(url_for('auth.login'))
    return render_template('auth_tg_bind.html', user=user, error='', flash='')


@auth_bp.route('/tg-bind', methods=['POST'])
def tg_bind_submit():
    """Привязывает telegram_id (из кода, сгенерированного ботом) к текущему аккаунту."""
    user = _user_from_cookie()
    if not user:
        return redirect(url_for('auth.login'))

    code = (request.form.get('code') or '').strip()
    entry = (LoginCode.query.filter_by(code=code, code_type='tg_bind', used=False)
             .order_by(LoginCode.id.desc()).first())
    if not entry or entry.created_at < datetime.utcnow() - timedelta(minutes=CODE_TTL_MINUTES):
        return render_template('auth_tg_bind.html', user=user,
                               error='Неверный или истёкший код', flash=''), 400

    # Проверяем, что этот telegram ещё не привязан к другому аккаунту
    tg_id = entry.telegram_id
    for u in get_panel_users():
        if str(u.get('telegramId', '')) == tg_id and u.get('id') != user['user_id']:
            return render_template('auth_tg_bind.html', user=user,
                                   error='Этот Telegram уже привязан к другому аккаунту', flash=''), 400

    res = update_panel_user_telegram(user['user_id'], tg_id)
    if not res['success']:
        return render_template('auth_tg_bind.html', user=user,
                               error=res.get('error', 'Ошибка привязки'), flash=''), 400

    entry.used = True
    db.session.commit()
    return render_template('auth_tg_bind.html', user=user, error='',
                           flash='✅ Telegram привязан! Теперь можно входить через бота и восстанавливать пароль.')


@auth_bp.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'GET':
        return render_template('auth_forgot.html', user=None, error='', flash='')

    username = (request.form.get('username') or '').strip()
    user = next((u for u in get_panel_users() if u.get('username') == username), None)
    if not user:
        return render_template('auth_forgot.html', user=None, error='Пользователь не найден', flash=''), 404

    tg_id = str(user.get('telegramId', ''))
    if not tg_id:
        return render_template('auth_forgot.html', user=None,
                               error='У этого аккаунта не привязан Telegram. Привяжите его, чтобы восстанавливать пароль.',
                               flash=''), 400

    with db.session.begin():
        code = _create_code(user['id'], 'reset')
    sent = _send_telegram(user['id'],
                          f"🔐 Код для восстановления пароля: {code.code}\nКод действует 15 минут.")
    if sent:
        flash_msg = 'Код отправлен в ваш Telegram. Введите его ниже.'
    else:
        flash_msg = 'Код сгенерирован. Не удалось отправить Telegram — введите код из бота ниже (см. раздел «Восстановление пароля» в боте).'
    return render_template('auth_reset.html', username=username, error='', flash=flash_msg), 200


@auth_bp.route('/reset', methods=['POST'])
def reset():
    username = (request.form.get('username') or '').strip()
    code = (request.form.get('code') or '').strip()
    password = request.form.get('password') or ''
    password2 = request.form.get('password2') or ''

    user = next((u for u in get_panel_users() if u.get('username') == username), None)
    if not user:
        return render_template('auth_reset.html', username=username, error='Пользователь не найден', flash=''), 404
    if len(password) < 6:
        return render_template('auth_reset.html', username=username, error='Пароль слишком короткий', flash=''), 400
    if password != password2:
        return render_template('auth_reset.html', username=username, error='Пароли не совпадают', flash=''), 400

    if not _verify_code(user['id'], code, 'reset'):
        return render_template('auth_reset.html', username=username, error='Неверный или истёкший код', flash=''), 400

    res = update_panel_user_password(user['id'], password)
    if not res['success']:
        return render_template('auth_reset.html', username=username, error=res.get('error', 'Ошибка смены пароля'), flash=''), 400

    ok, session_cookie, role, err = panel_login(username, password)
    if ok and session_cookie:
        resp = make_response(redirect(url_for('vpn_purchase.purchase_page')))
        resp.set_cookie('session', session_cookie, max_age=60 * 60 * 24 * 14,
                        samesite='Lax', httponly=False, path='/')
        return resp
    return render_template('auth_login.html', user=None,
                           error='Пароль изменён. Войдите с новым паролем.', flash='')


@auth_bp.route('/tg-login', methods=['GET', 'POST'])
def tg_login():
    """Вход через Telegram: юзер вводит код, полученный в боте."""
    if request.method == 'GET':
        return render_template('auth_tg_login.html', error='', flash='')

    code = (request.form.get('code') or '').strip()
    if len(code) < 4:
        return render_template('auth_tg_login.html', error='Введите код из Telegram-бота', flash=''), 400

    entry = (LoginCode.query.filter_by(code=code, code_type='tg_login', used=False)
             .order_by(LoginCode.id.desc()).first())
    if not entry or entry.created_at < datetime.utcnow() - timedelta(minutes=CODE_TTL_MINUTES):
        return render_template('auth_tg_login.html', error='Неверный или истёкший код', flash=''), 400

    user = get_panel_user(entry.user_id)
    if not user:
        return render_template('auth_tg_login.html', error='Пользователь не найден', flash=''), 404
    entry.used = True
    db.session.commit()

    from store.panel_session import create_session_cookie
    session_val = create_session_cookie(user['id'])
    if not session_val:
        return render_template('auth_tg_login.html', error='Ошибка создания сессии', flash=''), 500

    resp = make_response(redirect(url_for('vpn_purchase.purchase_page')))
    resp.set_cookie('session', session_val, max_age=60 * 60 * 24 * 14,
                    samesite='Lax', httponly=False, path='/')
    return resp


@auth_bp.route('/logout', methods=['GET'])
def logout():
    resp = make_response(redirect(url_for('auth.login')))
    resp.delete_cookie('session', path='/')
    return resp


def setup_auth(app):
    from store.modules.models import LoginCode  # noqa: F401 — регистрация модели в метаданных
    app.register_blueprint(auth_bp)
    logger.info("Auth module: настроен")


def panel_users():
    return get_panel_users()