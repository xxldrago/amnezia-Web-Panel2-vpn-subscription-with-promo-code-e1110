"""Доступ к данным Amnezia Web Panel (data.json) из Flask-системы store.

Amnezia-панель хранит пользователей/серверы/подключения в data.json.
store-контейнер монтирует тот же файл (read-only) через общее host volume,
чтобы получать актуальный список пользователей и серверов панели.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PANEL_DATA_FILE = os.environ.get('PANEL_DATA_FILE', '/app/data.json')


def load_panel_data() -> Dict[str, Any]:
    """Возвращает полное содержимое data.json панели (пустой dict, если нет)."""
    try:
        if os.path.exists(PANEL_DATA_FILE):
            with open(PANEL_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f) or {}
    except Exception as e:
        logger.error(f"Не удалось прочитать {PANEL_DATA_FILE}: {e}")
    return {}


def get_panel_users() -> List[Dict[str, Any]]:
    """Список пользователей панели."""
    return load_panel_data().get('users', [])


def get_panel_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает пользователя панели по его user_id (uuid)."""
    for u in get_panel_users():
        if u.get('id') == user_id:
            return u
    return None


def get_panel_servers() -> List[Dict[str, Any]]:
    """Список серверов панели."""
    data = load_panel_data()
    return data.get('servers', [])