"""Текст и картинка «Описание» — первое сообщение при нажатии «Начало» (событие bot_started)."""

from __future__ import annotations

import asyncio
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings
from app.services.storage import mutate_store, read_store

_PREFIX = "bot_started_desc"


def _guess_ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if path.endswith(ext):
            return ext
    return ".jpg"


def _remove_stored_files(parent: Path) -> None:
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        p = parent / f"{_PREFIX}{ext}"
        if p.is_file():
            p.unlink()


def _download_sync(url: str, dest: Path) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "check_subscribe-bot/1.0"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


async def resolve_bot_started_description_image_path() -> Path | None:
    data = await read_store()
    name = data.get("bot_started_description_file")
    if not name:
        return None
    p = (settings.DATA_JSON_PATH.parent / name).resolve()
    try:
        p.relative_to(settings.DATA_JSON_PATH.parent.resolve())
    except ValueError:
        return None
    if p.is_file():
        return p
    return None


async def replace_stored_bot_started_description_image(image_url: str) -> None:
    parent = settings.DATA_JSON_PATH.parent
    parent.mkdir(parents=True, exist_ok=True)
    ext = _guess_ext_from_url(image_url)
    filename = f"{_PREFIX}{ext}"
    dest = (parent / filename).resolve()
    try:
        dest.relative_to(parent.resolve())
    except ValueError:
        raise ValueError("invalid path") from None

    tmp = parent / ".bot_started_desc_download.tmp"
    try:
        await asyncio.to_thread(_download_sync, image_url, tmp)
        _remove_stored_files(parent)
        tmp.replace(dest)
    except Exception:
        if tmp.is_file():
            tmp.unlink()
        raise

    def _save(data: dict) -> None:
        data["bot_started_description_file"] = filename

    await mutate_store(_save)


async def delete_stored_bot_started_description_image() -> None:
    parent = settings.DATA_JSON_PATH.parent

    def _clear(data: dict) -> None:
        name = data.get("bot_started_description_file")
        if name:
            p = (parent / name).resolve()
            try:
                p.relative_to(parent.resolve())
            except ValueError:
                pass
            else:
                if p.is_file():
                    p.unlink()
        _remove_stored_files(parent)
        data["bot_started_description_file"] = None

    await mutate_store(_clear)


async def has_stored_bot_started_description_image() -> bool:
    p = await resolve_bot_started_description_image_path()
    return p is not None
