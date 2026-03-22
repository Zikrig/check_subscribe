import logging

from maxapi import Bot
from maxapi.exceptions.max import MaxApiError

from app.services.db import Channel
from app.services.storage import mutate_store, read_store

logger = logging.getLogger(__name__)


def _username_for_url(username: str) -> str:
    return username.strip().lstrip("@")


def normalized_channel_url(username: str, link: str | None) -> str:
    """Публичная ссылка на канал MAX (в клиенте обычно https://max.ru/@ник)."""
    if link:
        s = link.strip()
        if s.startswith(("http://", "https://")):
            return s
        if s.startswith("max.ru/"):
            return "https://" + s
    return f"https://max.ru/{_username_for_url(username)}"


async def resolve_channel_url(bot: Bot, channel: Channel) -> str:
    """Официальная ссылка из API, если бот видит чат; иначе из БД / шаблон max.ru/@…"""
    try:
        chat = await bot.get_chat_by_id(channel.id)
        if chat.link:
            return chat.link
    except Exception:
        pass
    return normalized_channel_url(channel.username, channel.link)


async def user_is_channel_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    """
    Проверка участия через GET …/members?user_ids=…
    Если список пуст (иногда так отвечает API), ищем пользователя в первых страницах списка.
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member is not None:
            return True
    except MaxApiError:
        return False
    except Exception:
        return False

    marker: int | None = None
    for _ in range(30):
        try:
            page = await bot.get_chat_members(chat_id, marker=marker, count=100)
        except Exception:
            return False
        for m in page.members:
            if m.user_id == user_id:
                return True
        marker = page.marker
        if marker is None:
            break
    return False


async def resolve_max_chat_id(bot: Bot, channel_id: int) -> int:
    """
    У MAX у каналов/чатов chat_id часто отрицательный. Если ввели +id без минуса,
    get_chat_by_id даёт 404 — тогда пробуем -id.
    """
    try:
        await bot.get_chat_by_id(channel_id)
        return channel_id
    except MaxApiError as e:
        if e.code != 404:
            return channel_id
    except Exception:
        return channel_id

    if channel_id <= 0:
        return channel_id

    alt = -channel_id
    try:
        await bot.get_chat_by_id(alt)
        logger.info(
            "chat_id исправлен: %s → %s (чат найден только с отрицательным id)",
            channel_id,
            alt,
        )
        return alt
    except Exception:
        return channel_id


def _row_to_channel(sid: str, row: dict) -> Channel:
    return Channel(
        id=int(sid),
        username=row["username"],
        name=row.get("name"),
        link=row.get("link"),
        is_active=row.get("is_active", True),
    )


async def get_all_channels():
    data = await read_store()
    channels = [
        _row_to_channel(sid, row) for sid, row in data["channels"].items()
    ]
    return sorted(channels, key=lambda c: c.id)


async def log_channels_at_startup(bot: Bot) -> None:
    """Пишет в лог все каналы из хранилища и сведения из MAX API (get_chat_by_id)."""
    channels = await get_all_channels()
    logger.info("Загружено каналов: %s", len(channels))
    for i, ch in enumerate(channels, start=1):
        logger.info(
            "  [%s] JSON: id=%s username=%s name=%s is_active=%s link=%s",
            i,
            ch.id,
            ch.username,
            ch.name,
            ch.is_active,
            ch.link,
        )
        try:
            chat = await bot.get_chat_by_id(ch.id)
            logger.info(
                "      MAX API: title=%r link=%s participants=%s is_public=%s",
                chat.title,
                chat.link,
                chat.participants_count,
                chat.is_public,
            )
        except MaxApiError as e:
            logger.warning("      MAX API: ошибка %s %s", e.code, e)
        except Exception as e:
            logger.warning("      MAX API: %s", e)

    by_abs: dict[int, list[int]] = {}
    for ch in channels:
        by_abs.setdefault(abs(ch.id), []).append(ch.id)
    for a, ids in by_abs.items():
        if len(set(ids)) > 1:
            logger.warning(
                "Одинаковый |id|=%s при разных знаках: %s — лишняя запись или ошибка без «-». "
                "Оставьте один id как в MAX (list_max_chats.py).",
                a,
                ids,
            )


async def get_channel(channel_id: int):
    data = await read_store()
    row = data["channels"].get(str(channel_id))
    if not row:
        return None
    return _row_to_channel(str(channel_id), row)


async def toggle_channel(channel_id: int):
    def _fn(data):
        row = data["channels"].get(str(channel_id))
        if row:
            row["is_active"] = not row.get("is_active", True)
            return True
        return False

    return await mutate_store(_fn)


async def update_channel(channel_id: int, name: str = None, link: str = None):
    def _fn(data):
        row = data["channels"].get(str(channel_id))
        if not row:
            return False
        if name is not None:
            row["name"] = name
        if link is not None:
            if not link.startswith(("https://", "http://", "max.ru/")):
                raise ValueError("Ссылка должна начинаться с https://, http:// или max.ru/")
            row["link"] = link
        return True

    return await mutate_store(_fn)


async def delete_channel(channel_id: int):
    def _fn(data):
        sid = str(channel_id)
        if sid in data["channels"]:
            del data["channels"][sid]
            return True
        return False

    return await mutate_store(_fn)


async def add_channel(channel_id: int, username: str, name: str = None, link: str = None):
    def _fn(data):
        sid = str(channel_id)
        if sid in data["channels"]:
            return False
        data["channels"][sid] = {
            "username": username,
            "name": name or username,
            "link": link or normalized_channel_url(username, None),
            "is_active": True,
        }
        return True

    return await mutate_store(_fn)
