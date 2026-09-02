"""Расшифровка Starlette-сессии (SessionMiddleware) из общего cookie `session`.

Amnezia Web Panel использует Starlette SessionMiddleware, который сериализует
словарь сессии через itsdangerous.URLSafeSerializer в cookie `session`.
Панель кладёт в сессию ключ `user_id`.

Чтобы Flask-система (store) видела того же пользователя без изменения панели,
мы расшифровываем ту же cookie, используя тот же SECRET_KEY. Для этого SECRET_KEY
должен быть одинаковым в .env панели и store.
"""
import hashlib
import logging
import os
from typing import Optional

try:
    from itsdangerous import URLSafeSerializer, BadSignature, SignatureExpired
except ImportError:  # pragma: no cover
    from itsdangerous import URLSafeSerializer
    BadSignature = Exception
    SignatureExpired = Exception

logger = logging.getLogger(__name__)


def _get_serializer(secret_key: str):
    """Создаёт такой же URLSafeSerializer, какой использует Starlette SessionMiddleware."""
    return URLSafeSerializer(
        secret_key,
        salt='cookie-session',
        serializer=None,               # стандартный defaults
        signer_kwargs={
            'key_derivation': 'hmac',
            'digest_method': hashlib.sha1,
        },
    )


def decode_session_cookie(cookie_value: str, secret_key: Optional[str] = None) -> dict:
    """Возвращает словарь сессии из cookie `session`, либо пустой dict."""
    if not cookie_value:
        return {}
    secret_key = secret_key or os.environ.get('SECRET_KEY', '')
    if not secret_key:
        logger.warning("SECRET_KEY не задан — невозможно прочитать сессию панели.")
        return {}
    try:
        serializer = _get_serializer(secret_key)
        return serializer.loads(cookie_value, max_age=60 * 60 * 24 * 14)
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