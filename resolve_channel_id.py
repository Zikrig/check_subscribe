"""
Тестовый скрипт: узнать chat_id канала в MAX всеми доступными способами (maxapi).

Запуск из корня проекта:
  pip install maxapi python-dotenv
  python resolve_channel_id.py "https://max.ru/channelname"
  python resolve_channel_id.py "@channelname"
  python resolve_channel_id.py -1001234567890

Токен: MAX_BOT_TOKEN или BOT_TOKEN в .env

Способы:
  A) get_chat_by_id      — если ввод — целое число: пробуем id и -id (как resolve_max_chat_id)
  B) get_chat_by_link    — по ссылке/нику (нормализация как в app.services.channels)
  C) get_chats           — поиск в диалогах бота по подстроке в link / title
  D) get_me_from_chat    — проверка, что бот состоит в чате (для найденных id)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

from maxapi import Bot
from maxapi.exceptions.max import MaxApiError


def _nick_hint_from_url(normalized: str) -> str:
    p = urlparse(normalized)
    tail = (p.path or "").strip("/").split("/")[-1]
    return tail.lstrip("@") if tail else ""


def _is_int_string(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    try:
        int(s)
        return True
    except ValueError:
        return False


async def try_get_chat_by_link(bot: Bot, link: str) -> tuple[bool, str, int | None]:
    try:
        chat = await bot.get_chat_by_link(link)
        return True, f"title={chat.title!r} link={chat.link!r}", chat.chat_id
    except ValueError as e:
        return False, str(e), None
    except MaxApiError as e:
        return False, f"API {e.code} {e}", None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", None


async def try_get_chat_by_id(bot: Bot, chat_id: int) -> tuple[bool, str, int | None]:
    try:
        chat = await bot.get_chat_by_id(chat_id)
        return True, f"title={chat.title!r} link={chat.link!r}", chat.chat_id
    except MaxApiError as e:
        return False, f"API {e.code} {e}", None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", None


async def try_get_chats_match(bot: Bot, nick_hint: str) -> list[tuple[int, str, str]]:
    nick_hint = nick_hint.lower().strip().lstrip("@")
    found: list[tuple[int, str, str]] = []
    marker: int | None = None
    while True:
        page = await bot.get_chats(count=100, marker=marker)
        for chat in page.chats:
            link = (chat.link or "").lower()
            title = (chat.title or "").lower()
            if nick_hint and (
                nick_hint in link
                or link.rstrip("/").endswith("/" + nick_hint)
                or nick_hint in title
            ):
                found.append(
                    (chat.chat_id, chat.title or "", chat.link or "")
                )
        marker = page.marker
        if marker is None:
            break
    return found


async def try_get_me_from_chat(bot: Bot, chat_id: int) -> tuple[bool, str]:
    try:
        me = await bot.get_me_from_chat(chat_id)
        return True, f"bot user_id={me.user_id} is_admin={getattr(me, 'is_admin', '?')}"
    except MaxApiError as e:
        return False, f"API {e.code} (бот не в чате или нет доступа)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Узнать chat_id канала MAX разными способами"
    )
    parser.add_argument(
        "input",
        help="Ссылка, @ник, ник или числовой chat_id",
    )
    args = parser.parse_args()

    token = os.getenv("MAX_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        print("Ошибка: задайте MAX_BOT_TOKEN или BOT_TOKEN в .env", file=sys.stderr)
        sys.exit(1)

    raw = args.input.strip()
    print(f"Ввод: {raw!r}\n")
    print("=" * 72)

    from app.services.channels import normalize_channel_link_input

    bot = Bot(token=token)
    ids_seen: set[int] = set()

    try:
        # --- A) Только число: get_chat_by_id (id и -id) ---
        if _is_int_string(raw):
            n = int(raw)
            print("Ввод — число: пробуем get_chat_by_id для id и -id\n")
            for label, cid in (
                ("как в вводе", n),
                ("противоположный знак", -n),
            ):
                ok, detail, got = await try_get_chat_by_id(bot, cid)
                print(f"  [A] get_chat_by_id ({label}: {cid})")
                print(f"      {'OK' if ok else 'FAIL'} — {detail}")
                if ok and got is not None:
                    ids_seen.add(got)
                    m_ok, m_det = await try_get_me_from_chat(bot, got)
                    print(
                        f"      get_me_from_chat: {'OK' if m_ok else 'FAIL'} — {m_det}"
                    )
            if ids_seen:
                print("\n" + "=" * 72)
                print("Итог: chat_id =", sorted(ids_seen))
            else:
                print(
                    "\n  По числу не найдено. Укажите публичную ссылку или @ник "
                    "(число могло быть неверным или чат недоступен боту)."
                )
            return

        # --- B) Ссылка / @ник / ник ---
        try:
            normalized = normalize_channel_link_input(raw)
        except ValueError as e:
            print(f"[B] normalize (как в боте): FAIL — {e}")
            print("\n" + "=" * 72)
            print("Не удалось разобрать ввод.")
            return

        print(f"[0] Нормализация: {normalized!r}\n")

        ok, detail, got = await try_get_chat_by_link(bot, normalized)
        print(f"[B] get_chat_by_link")
        print(f"    {'OK' if ok else 'FAIL'} — {detail}")
        if ok and got is not None:
            ids_seen.add(got)
            m_ok, m_det = await try_get_me_from_chat(bot, got)
            print(f"    get_me_from_chat: {'OK' if m_ok else 'FAIL'} — {m_det}")

        nick = _nick_hint_from_url(normalized)
        if nick:
            print(f"\n[C] get_chats — поиск по подсказке «{nick}» (link содержит ник / title)")
            matches = await try_get_chats_match(bot, nick)
            if not matches:
                print(
                    "    Нет совпадений: бот не в чате с таким ником в списке диалогов "
                    "или другой формат ссылки."
                )
            else:
                for cid, title, link in matches:
                    print(f"    chat_id={cid}  title={title!r}  link={link!r}")
                    ids_seen.add(cid)
                    m_ok, m_det = await try_get_me_from_chat(bot, cid)
                    print(
                        f"      get_me_from_chat: {'OK' if m_ok else 'FAIL'} — {m_det}"
                    )

        print("\n" + "=" * 72)
        if ids_seen:
            print("Найденные chat_id:", sorted(ids_seen))
        else:
            print(
                "chat_id не получен. Проверьте ссылку и что бот добавлен в канал "
                "или попробуйте числовой id из клиента MAX."
            )

    finally:
        await bot.close_session()


if __name__ == "__main__":
    asyncio.run(main())
