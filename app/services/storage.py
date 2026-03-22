"""Персистентное хранилище в одном JSON-файле (async, с блокировкой)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.config import settings

T = TypeVar("T")

_lock = asyncio.Lock()


def _empty_store() -> dict[str, Any]:
    return {
        "promos": {},
        "replics": {},
        "channels": {},
        "counters": {"promos_issued": 0},
        "start_image_file": None,
        "promo_followup_file": None,
        "promo_followup_button_url": None,
        "bot_started_description_file": None,
    }


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    base = _empty_store()
    for key in base:
        if key not in data:
            data[key] = base[key]
        elif key == "counters" and isinstance(data[key], dict):
            for ck, cv in base["counters"].items():
                data["counters"].setdefault(ck, cv)
    return data


def _load_sync(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_store()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return _empty_store()
    return _normalize(data)


def _save_sync(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


async def read_store() -> dict[str, Any]:
    async with _lock:
        return _load_sync(settings.DATA_JSON_PATH)


async def write_store(data: dict[str, Any]) -> None:
    async with _lock:
        _save_sync(settings.DATA_JSON_PATH, data)


async def mutate_store(fn: Callable[[dict[str, Any]], T]) -> T:
    async with _lock:
        data = _load_sync(settings.DATA_JSON_PATH)
        result = fn(data)
        _save_sync(settings.DATA_JSON_PATH, data)
        return result


async def init_storage() -> None:
    """
    Создаёт файл при отсутствии, дополняет счётчики при необходимости.

    Каналы из .env (CHANNELS) подмешиваются только если store.json ещё не было —
    первый запуск. Если файл уже есть, список каналов берётся только из JSON
    (управление через /channels в боте).
    """
    async with _lock:
        path = settings.DATA_JSON_PATH
        file_existed = path.exists()
        if not file_existed:
            data = _empty_store()
        else:
            data = _load_sync(path)
        data = _normalize(data)
        changed = False

        if not file_existed:
            for ch in settings.CHANNELS:
                sid = str(ch["id"])
                if sid not in data["channels"]:
                    un = ch["username"]
                    data["channels"][sid] = {
                        "username": un,
                        "name": un,
                        "link": None,
                        "is_active": True,
                    }
                    changed = True
        if data["counters"].get("promos_issued") is None:
            data["counters"]["promos_issued"] = 0
            changed = True
        if changed or not path.exists():
            _save_sync(path, data)
