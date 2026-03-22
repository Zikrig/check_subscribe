"""Стартовая картинка: из store (через админку) или fallback START_IMAGE_PATH."""

from __future__ import annotations

import asyncio
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings
from app.services.storage import mutate_store, read_store

_START_WELCOME_PREFIX = "start_welcome"


def _guess_ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if path.endswith(ext):
            return ext
    return ".jpg"


async def resolve_start_image_path() -> Path | None:
    """Файл из store (если есть) иначе START_IMAGE_PATH при существующем файле."""
    data = await read_store()
    name = data.get("start_image_file")
    if name:
        p = (settings.DATA_JSON_PATH.parent / name).resolve()
        try:
            p.relative_to(settings.DATA_JSON_PATH.parent.resolve())
        except ValueError:
            return None
        if p.is_file():
            return p
    env = settings.START_IMAGE_PATH
    if env is not None and env.is_file():
        return env
    return None


def _remove_stored_image_files(parent: Path) -> None:
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        p = parent / f"{_START_WELCOME_PREFIX}{ext}"
        if p.is_file():
            p.unlink()


def _download_sync(url: str, dest: Path) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "check_subscribe-bot/1.0"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


async def replace_stored_start_image(image_url: str) -> None:
    """Скачивает картинку в каталог data, имя фиксированное start_welcome.<ext>."""
    parent = settings.DATA_JSON_PATH.parent
    parent.mkdir(parents=True, exist_ok=True)
    ext = _guess_ext_from_url(image_url)
    filename = f"{_START_WELCOME_PREFIX}{ext}"
    dest = (parent / filename).resolve()
    try:
        dest.relative_to(parent.resolve())
    except ValueError:
        raise ValueError("invalid path") from None

    tmp = parent / ".start_welcome_download.tmp"
    try:
        await asyncio.to_thread(_download_sync, image_url, tmp)
        _remove_stored_image_files(parent)
        tmp.replace(dest)
    except Exception:
        if tmp.is_file():
            tmp.unlink()
        raise

    def _save(data: dict) -> None:
        data["start_image_file"] = filename

    await mutate_store(_save)


async def delete_stored_start_image() -> None:
    parent = settings.DATA_JSON_PATH.parent

    def _clear(data: dict) -> None:
        name = data.get("start_image_file")
        if name:
            p = (parent / name).resolve()
            try:
                p.relative_to(parent.resolve())
            except ValueError:
                pass
            else:
                if p.is_file():
                    p.unlink()
        _remove_stored_image_files(parent)
        data["start_image_file"] = None

    await mutate_store(_clear)


def _looks_like_image_path(name: str) -> bool:
    lower = name.lower()
    return any(
        lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")
    )


def first_image_url_from_message_body(body) -> str | None:
    """URL картинки: вложение image или file с расширением изображения."""
    if not body or not body.attachments:
        return None
    from maxapi.enums.attachment import AttachmentType

    for att in body.attachments:
        t = att.type
        if att.payload is None:
            continue
        url = getattr(att.payload, "url", None)
        if not url:
            continue

        if t == AttachmentType.IMAGE or t == "image":
            return url

        if t == AttachmentType.FILE or t == "file":
            fn = getattr(att, "filename", None) or ""
            if _looks_like_image_path(fn):
                return url
            path = urlparse(url).path
            if _looks_like_image_path(path):
                return url

    return None


async def has_stored_start_image() -> bool:
    data = await read_store()
    name = data.get("start_image_file")
    if not name:
        return False
    p = (settings.DATA_JSON_PATH.parent / name).resolve()
    return p.is_file()
