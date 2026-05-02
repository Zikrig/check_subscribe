import logging
import re
from re import findall
from typing import Any

from maxapi import Bot
from maxapi.enums.chat_type import ChatType
from maxapi.exceptions.max import MaxApiError

# Как в maxapi.methods.get_chat_by_link.GetChatByLink.PATTERN_LINK
_LINK_USERNAME_PATTERN = r"@?[a-zA-Z]+[a-zA-Z0-9-_]*"

from app.services.db import Channel
from app.services.storage import mutate_store, read_store

logger = logging.getLogger(__name__)

def _chat_summary_for_log(chat: Any) -> dict[str, Any]:
    t = getattr(chat, "type", None)
    tv = getattr(t, "value", None) if t is not None else None
    return {
        "chat_id": getattr(chat, "chat_id", None),
        "type": tv or (str(t) if t is not None else None),
        "title": getattr(chat, "title", None),
        "link": getattr(chat, "link", None),
    }


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
    """Официальная ссылка из API, если бот видит чат; иначе из JSON / шаблон max.ru/@…"""
    try:
        chat = await bot.get_chat_by_id(channel["id"])
        if chat.link:
            return chat.link
    except Exception:
        pass
    return normalized_channel_url(channel["username"], channel["link"])


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


def _username_tail_from_link_string(link: str) -> str:
    """Последний фрагмент, по которому MAX резолвит чат в GET /chats/{link} (как в maxapi)."""
    parts = findall(_LINK_USERNAME_PATTERN, link)
    if not parts:
        raise ValueError(
            "Не удалось извлечь ник из ссылки. Проверьте формат: https://max.ru/ник (без @ в пути)."
        )
    return parts[-1].lstrip("@")


def normalize_channel_link_input(raw: str) -> str:
    """
    Приводит ввод к URL вида https://max.ru/ник без «@» в пути (как публичная ссылка в MAX).
    Допустимо: полный URL, max.ru/…, @ник или просто ник.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("Пустая строка.")
    low = raw.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return re.sub(r"(max\.ru)/@", r"\1/", raw, flags=re.IGNORECASE)
    if low.startswith("max.ru"):
        slash = raw.find("/")
        if slash >= 0:
            tail = raw[slash + 1 :].lstrip("@")
        else:
            tail = raw[6:].lstrip("/").lstrip("@")
        if not tail:
            raise ValueError("Укажите ник в ссылке: max.ru/ник")
        return f"https://max.ru/{tail}"
    if raw.startswith("@"):
        nick = raw[1:].strip().lstrip("@")
        if not nick:
            raise ValueError("Укажите ник после @.")
        return f"https://max.ru/{nick}"
    nick = raw.strip().lstrip("@")
    if not nick:
        raise ValueError("Укажите ссылку https://max.ru/ник или ник / @ник.")
    return f"https://max.ru/{nick}"


def _looks_like_numeric_chat_id(raw: str) -> bool:
    s = raw.strip()
    if not s:
        return False
    if s[0] == "-":
        s = s[1:]
        if not s:
            return False
    return s.isdigit()


def _username_from_resolved_chat(chat, resolved_chat_id: int) -> str:
    link = getattr(chat, "link", None) or ""
    if link:
        try:
            return _username_tail_from_link_string(link)
        except ValueError:
            pass
    title = (chat.title or "").strip()
    if title:
        return title[:128]
    return str(abs(resolved_chat_id))


async def _matching_channels_for_bot(bot: Bot, nick_hint: str) -> list:
    """
    Среди чатов, где состоит бот — только каналы (type=channel).
    Пагинация get_chats; отбор по нику в ссылке или названии.
    """
    nick_hint = nick_hint.lower().strip().lstrip("@")
    if not nick_hint:
        return []
    out: list = []
    marker: int | None = None
    pages = 0
    inspected = 0
    skipped_dialog = 0
    skipped_group_chat = 0
    channels_seen = 0
    membership_channel_ids: list[int] = []
    while True:
        page = await bot.get_chats(count=100, marker=marker)
        pages += 1
        for chat in page.chats:
            inspected += 1
            if chat.type == ChatType.DIALOG:
                skipped_dialog += 1
                continue
            if chat.type == ChatType.CHAT:
                skipped_group_chat += 1
                continue
            if chat.type != ChatType.CHANNEL:
                continue
            channels_seen += 1
            membership_channel_ids.append(chat.chat_id)
            c_link = (chat.link or "").lower()
            title = (chat.title or "").lower()
            if (
                nick_hint in c_link
                or c_link.rstrip("/").endswith("/" + nick_hint)
                or nick_hint in title
            ):
                out.append(chat)
        marker = page.marker
        if marker is None:
            break
    matched_ids = [c.chat_id for c in out]
    logger.info(
        "добавление канала: обход членства бота только channel (get_chats), страниц=%s, "
        "чатов всего=%s, пропуск dialog=%s, пропуск group chat=%s, каналов просмотрено=%s; "
        "id всех каналов где бот (membership)=%s; совпало по нику=%s id каналов (совпадения)=%s",
        pages,
        inspected,
        skipped_dialog,
        skipped_group_chat,
        channels_seen,
        membership_channel_ids,
        len(out),
        matched_ids,
    )
    return out


async def resolve_channel_from_chat_id_only(
    bot: Bot, channel_id: int
) -> tuple[int, str, str | None, str | None]:
    """
    Добавление канала только по числовому chat_id: GET /chats/{id}.
    Никакого обхода get_chats.
    """
    logger.info("добавление канала: поиск по id %s", channel_id)

    resolved_id = await resolve_max_chat_id(bot, channel_id)
    try:
        chat = await bot.get_chat_by_id(resolved_id)
    except MaxApiError as e:
        logger.warning(
            "добавление канала: поиск по id %s — ошибка API %s (%s)",
            channel_id,
            e.code,
            e,
        )
        raise ValueError(
            f"Канал с chat_id={channel_id} не найден или недоступен (API {e.code}). "
            "Проверьте id (учёт знака «-») и что бот добавлен администратором в канал."
        ) from e
    except Exception as e:
        logger.warning("добавление канала: поиск по id %s — %s", channel_id, e)
        raise ValueError(
            f"Не удалось получить канал по chat_id={channel_id}: {e}"
        ) from e

    final_id = await resolve_max_chat_id(bot, chat.chat_id)
    username = _username_from_resolved_chat(chat, final_id)
    name = chat.title or username
    stored_link = chat.link or normalized_channel_url(username, None)
    logger.info(
        "добавление канала: поиск по id %s — ответ %s chat_id канала=%s",
        channel_id,
        _chat_summary_for_log(chat),
        getattr(chat, "chat_id", None),
    )
    return final_id, username, name, stored_link


async def resolve_channel_from_link_only(
    bot: Bot, link: str
) -> tuple[int, str, str | None, str | None]:
    """
    Один ввод: ссылка или ник — внутри нормализуется в https://max.ru/ник.
    Сначала get_chat_by_link; если нет — только среди каналов (type channel), где состоит бот.
    Возвращает (chat_id, username, name, link) для add_channel.
    """
    link_norm = normalize_channel_link_input(link)
    nick_hint = _username_tail_from_link_string(link_norm)

    logger.info(
        "добавление канала: поиск по нику/ссылке %r → %s (ник %s)",
        link,
        link_norm,
        nick_hint,
    )

    try:
        chat = await bot.get_chat_by_link(link_norm)
        logger.info(
            "добавление канала: поиск по нику %s через get_chat_by_link — ответ %s chat_id канала=%s",
            nick_hint,
            _chat_summary_for_log(chat),
            getattr(chat, "chat_id", None),
        )
    except (ValueError, MaxApiError) as e:
        logger.info(
            "добавление канала: get_chat_by_link не удался для %s (%s), "
            "пробую среди каналов членства бота",
            nick_hint,
            type(e).__name__,
        )
        matches = await _matching_channels_for_bot(bot, nick_hint)
        match_ids = [c.chat_id for c in matches]
        if len(matches) == 1:
            chat = matches[0]
            logger.info(
                "добавление канала: поиск по нику %s среди каналов бота — ответ %s chat_id канала=%s "
                "(все найденные id=%s)",
                nick_hint,
                _chat_summary_for_log(chat),
                getattr(chat, "chat_id", None),
                match_ids,
            )
        elif len(matches) > 1:
            logger.warning(
                "добавление канала: по нику %s несколько каналов (%s шт.), id каналов (все)=%s",
                nick_hint,
                len(matches),
                match_ids,
            )
            raise ValueError(
                "Найдено несколько каналов с таким ником среди членства бота; "
                "уточните ссылку или укажите числовой chat_id."
            ) from e
        else:
            if isinstance(e, MaxApiError):
                logger.warning(
                    "добавление канала: нику %s среди каналов бота нет (совпадения id=[]), было API %s",
                    nick_hint,
                    e.code,
                )
                raise ValueError(
                    f"Канал по ссылке недоступен (код {e.code}). "
                    "Среди каналов бота совпадений по нику нет — укажите chat_id канала или проверьте ввод."
                ) from e
            logger.warning(
                "добавление канала: нику %s среди каналов бота нет (совпадения id=[]), причина: %s",
                nick_hint,
                e,
            )
            raise ValueError(
                f"Не удалось разрешить канал по нику «{nick_hint}»: {e}. "
                "Среди каналов бота не найдено; уточните ссылку или chat_id."
            ) from e

    username = nick_hint
    channel_id = await resolve_max_chat_id(bot, chat.chat_id)
    name = chat.title or username
    stored_link = chat.link or normalized_channel_url(username, None)
    logger.info(
        "добавление канала: итог по нику %s chat_id канала=%s username=%s",
        nick_hint,
        channel_id,
        username,
    )
    return channel_id, username, name, stored_link


async def parse_admin_channel_input(
    bot: Bot, text: str
) -> tuple[int, str, str | None, str | None]:
    """Одна строка: chat_id (целое), ссылка (https://max.ru/ник) или коротко @ник / ник."""
    text = text.strip()
    if not text:
        raise ValueError("Пустой ввод.")
    if _looks_like_numeric_chat_id(text):
        return await resolve_channel_from_chat_id_only(bot, int(text.strip()))
    return await resolve_channel_from_link_only(bot, text)


def _row_to_channel(sid: str, row: dict) -> Channel:
    return {
        "id": int(sid),
        "username": row["username"],
        "name": row.get("name"),
        "link": row.get("link"),
        "is_active": row.get("is_active", True),
    }


async def get_all_channels():
    data = await read_store()
    channels = [
        _row_to_channel(sid, row) for sid, row in data["channels"].items()
    ]
    return sorted(channels, key=lambda c: c["id"])


async def log_channels_at_startup(bot: Bot) -> None:
    """Пишет в лог все каналы из хранилища и сведения из MAX API (get_chat_by_id)."""
    channels = await get_all_channels()
    logger.info("Загружено каналов: %s", len(channels))
    for i, ch in enumerate(channels, start=1):
        logger.info(
            "  [%s] JSON: id=%s username=%s name=%s is_active=%s link=%s",
            i,
            ch["id"],
            ch["username"],
            ch["name"],
            ch["is_active"],
            ch["link"],
        )
        try:
            chat = await bot.get_chat_by_id(ch["id"])
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
        by_abs.setdefault(abs(ch["id"]), []).append(ch["id"])
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
