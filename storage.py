# -*- coding: utf-8 -*-
"""
Oddiy JSON asosidagi saqlash: foydalanuvchilar ro'yxati, texnik ishlar rejimi,
statistika.

E'TIBOR: Render kabi hostinglarda fayl tizimi vaqtinchalik bo'lishi mumkin -
qayta deploy qilinganda state.json yo'qolishi mumkin. Asosiy jadval
ma'lumotlari data.py da alohida saqlanadi, shuning uchun bu xavfli emas.

Yaxshilanishlar:
  * ma'lumot xotirada keshlanadi (har tugma bosilganda fayl o'qilmaydi)
  * fayl atomik yoziladi (vaqtinchalik fayl + os.replace) - buzilmaydi
  * ichki ro'yxat/lug'atlar deepcopy qilinadi (umumiy default holat yo'q)
"""

import copy
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_FILE_PATH = os.environ.get(
    "STATE_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
)

_DEFAULT_STATE = {
    "users": [],  # chat_id lar ro'yxati (broadcast uchun)
    "maintenance": False,  # texnik ishlar rejimi
    "action_counts": {},  # {"stu:schedule": 12, ...} - statistika uchun
}

_state = None  # xotiradagi kesh


def _read_file():
    if not os.path.exists(_FILE_PATH):
        return copy.deepcopy(_DEFAULT_STATE)
    try:
        with open(_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("state.json lug'at emas")
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("state.json o'qilmadi (%s), bo'sh holat bilan boshlanadi", exc)
        # buzilgan faylni yo'qotmaslik uchun nusxasini saqlab qo'yamiz
        try:
            os.replace(_FILE_PATH, _FILE_PATH + ".broken")
        except OSError:
            pass
        return copy.deepcopy(_DEFAULT_STATE)
    for key, value in _DEFAULT_STATE.items():
        data.setdefault(key, copy.deepcopy(value))
    return data


def _get_state():
    global _state
    if _state is None:
        _state = _read_file()
    return _state


def _save(state):
    tmp_path = _FILE_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, _FILE_PATH)
    except OSError as exc:
        # Diskka yozib bo'lmasa ham bot ishlashda davom etadi (xotirada saqlanadi)
        logger.warning("state.json yozilmadi: %s", exc)


def register_user(chat_id: int):
    with _LOCK:
        state = _get_state()
        if chat_id not in state["users"]:
            state["users"].append(chat_id)
            _save(state)


def remove_user(chat_id: int):
    with _LOCK:
        state = _get_state()
        if chat_id in state["users"]:
            state["users"].remove(chat_id)
            _save(state)


def get_all_users():
    with _LOCK:
        return list(_get_state()["users"])


def is_maintenance() -> bool:
    with _LOCK:
        return bool(_get_state()["maintenance"])


def toggle_maintenance() -> bool:
    with _LOCK:
        state = _get_state()
        state["maintenance"] = not state["maintenance"]
        _save(state)
        return state["maintenance"]


def log_action(action: str):
    with _LOCK:
        state = _get_state()
        state["action_counts"][action] = state["action_counts"].get(action, 0) + 1
        _save(state)


def get_stats():
    with _LOCK:
        state = _get_state()
        return {
            "user_count": len(state["users"]),
            "action_counts": dict(state["action_counts"]),
        }
