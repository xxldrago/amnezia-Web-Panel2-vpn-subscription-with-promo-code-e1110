"""Расшифровка Starlette-сессии (SessionMiddleware) из общего cookie `session`.

Amnezia Web Panel использует Starlette SessionMiddleware. Начиная со Starlette,
SessionMiddleware хранит сессию как TimestampSigner(secret).sign(b64encode(json(dict))).
Панель кладёт в сессию ключ `user_id`.

Чтобы Flask-система (store) видела того же пользователя без изменения панели,
мы расшифровываем и генерируем ту же cookie, используя тот же SECRET_KEY.
Для этого SECRET_KEY должен быть одинаковым в .env панели и store.
"""
import base64
import json
import logging
import os
from typing import Optional

from itsdangerous import TimestampSigner, BadSignature, SignatureExpired

logger = logging.getLogger(__name__)

SESSION_MAX_AGE = 14 * 24 * 60 * 60  # 14 дней (совпадает с панелью)


def _get_signer(secret_key: str) -> TimestampSigner:
    return TimestampSigner(secret_key)


def decode_session_cookie(cookie_value: str, secret_key: Optional[str] = None) -> dict:
    """Возвращает словарь сессии из cookie `session`, либо пустой dict."""
    if not cookie_value:
        return {}
    secret_key = secret_key or os.environ.get('SECRET_KEY', '')
    if not secret_key:
        logger.warning("SECRET_KEY не задан — невозможно прочитать сессию панели.")
        return {}
    try:
        signer = _get_signer(secret_key)
        data = signer.unsign(cookie_value.encode('utf-8'), max_age=SESSION_MAX_AGE)
        return json.loads(base64.b64decode(data))
    except SignatureExpired:
        logger.info("Сессия пользователя истекла.")
        return {}
    except BadSignature:
        # Cookie не подписана нашим ключом — пользователь не авторизован в панели
        return {}
    except Exception as e:
        logger.error(f"Не удалось расшифровать сессию панели: {e}")
        return {}


def get_panel_user_id(cookie_header: str = '', secret_key: Optional[str] = None) -> Optional[str]:
    """Извлекает user_id из cookie `session` (если пользователь вошёл в панель)."""
    session = decode_session_cookie(cookie_header, secret_key)
    return session.get('user_id')


def create_session_cookie(user_id: str, secret_key: Optional[str] = None) -> str:
    """Генерирует валидную cookie-сессию панели для user_id.

    Используется для «входа через Telegram»: store сам создаёт тот же Starlette cookie,
    который панель примет как авторизацию данного пользователя (общий SECRET_KEY).
    """
    secret_key = secret_key or os.environ.get('SECRET_KEY', '')
    if not secret_key:
        return ''
    data = base64.b64encode(json.dumps({'user_id': user_id}).encode('utf-8'))
    signer = _get_signer(secret_key)
    return signer.sign(data).decode('utf-8')