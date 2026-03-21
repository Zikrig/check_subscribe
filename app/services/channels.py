import logging

from sqlalchemy import select

from maxapi import Bot
from maxapi.exceptions.max import MaxApiError

from app.services.db import SessionLocal, Channel

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

async def get_all_channels():
    async with SessionLocal() as session:
        result = await session.execute(select(Channel))
        return result.scalars().all()


async def log_channels_at_startup(bot: Bot) -> None:
    """Пишет в лог все каналы из БД и сведения из MAX API (get_chat_by_id)."""
    channels = await get_all_channels()
    logger.info("Загружено каналов: %s", len(channels))
    for i, ch in enumerate(channels, start=1):
        logger.info(
            "  [%s] БД: id=%s username=%s name=%s is_active=%s link=%s",
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


async def get_channel(channel_id: int):
    async with SessionLocal() as session:
        return await session.get(Channel, channel_id)

async def toggle_channel(channel_id: int):
    async with SessionLocal() as session:
        channel = await session.get(Channel, channel_id)
        if channel:
            channel.is_active = not channel.is_active
            await session.commit()
            return True
    return False

async def update_channel(channel_id: int, name: str = None, link: str = None):
    async with SessionLocal() as session:
        channel = await session.get(Channel, channel_id)
        if channel:
            if name is not None:
                channel.name = name
            if link is not None:
                # Validate link format
                if not link.startswith(('https://', 'http://', 'max.ru/')):
                    raise ValueError("Ссылка должна начинаться с https://, http:// или max.ru/")
                channel.link = link
            await session.commit()
            return True
    return False

async def delete_channel(channel_id: int):
    async with SessionLocal() as session:
        channel = await session.get(Channel, channel_id)
        if channel:
            await session.delete(channel)
            await session.commit()
            return True
    return False

async def add_channel(channel_id: int, username: str, name: str = None, link: str = None):
    async with SessionLocal() as session:
        # Проверяем, нет ли уже канала с таким id
        existing = await session.get(Channel, channel_id)
        if existing:
            return False  # уже существует
            
        new_channel = Channel(
            id=channel_id,
            username=username,
            name=name or username,
            link=link or normalized_channel_url(username, None),
            is_active=True
        )
        session.add(new_channel)
        await session.commit()
        return True