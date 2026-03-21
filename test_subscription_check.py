"""
Скрипт: все варианты проверки «подписан ли user_id на канал chat_id» в MAX API.

Запуск из корня проекта (нужен токен бота в .env):
  pip install maxapi python-dotenv
  python test_subscription_check.py --chat-id -100123456789 --user-id 220372600

Переменные окружения (как у бота):
  MAX_BOT_TOKEN или BOT_TOKEN

Подходы:
  1) get_chat_by_id        — бот видит чат и ссылку (права/участие бота)
  2) get_me_from_chat      — бот сам состоит в чате
  3) get_chat_member       — maxapi: members с фильтром user_ids
  4) get_chat_members      — явный запрос с user_ids=[user_id]
  5) Постраничный список   — без user_ids, поиск user_id в members
  6) user_is_channel_member — как в приложении (3 + 5)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv


# Совпадает с app.services.channels.user_is_channel_member (без импорта app → без БД/SQLAlchemy).
async def user_is_channel_member_like_prod(bot, chat_id: int, user_id: int) -> bool:
    from maxapi.exceptions.max import MaxApiError

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


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str


def _fmt_exc(e: BaseException) -> str:
    return f"{e.__class__.__name__}: {e}"


async def approach_get_chat_by_id(bot, chat_id: int) -> StepResult:
    from maxapi.exceptions.max import MaxApiError

    try:
        chat = await bot.get_chat_by_id(chat_id)
        link = chat.link or "(нет link)"
        return StepResult(
            name="get_chat_by_id",
            ok=True,
            detail=f"title={chat.title!r} link={link} participants={chat.participants_count}",
        )
    except MaxApiError as e:
        return StepResult(
            name="get_chat_by_id",
            ok=False,
            detail=f"API {e.code} {_fmt_exc(e)}",
        )
    except Exception as e:
        return StepResult(name="get_chat_by_id", ok=False, detail=_fmt_exc(e))


async def approach_get_me_from_chat(bot, chat_id: int) -> StepResult:
    from maxapi.exceptions.max import MaxApiError

    try:
        me = await bot.get_me_from_chat(chat_id)
        return StepResult(
            name="get_me_from_chat",
            ok=True,
            detail=f"bot user_id={me.user_id} is_admin={me.is_admin}",
        )
    except MaxApiError as e:
        return StepResult(
            name="get_me_from_chat",
            ok=False,
            detail=f"API {e.code} (бот не в чате или нет доступа) {_fmt_exc(e)}",
        )
    except Exception as e:
        return StepResult(name="get_me_from_chat", ok=False, detail=_fmt_exc(e))


async def approach_get_chat_member(bot, chat_id: int, user_id: int) -> StepResult:
    from maxapi.exceptions.max import MaxApiError

    try:
        m = await bot.get_chat_member(chat_id, user_id)
        if m is None:
            return StepResult(
                name="get_chat_member (maxapi)",
                ok=True,
                detail="ответ 200, members пуст — пользователь не найден фильтром user_ids",
            )
        return StepResult(
            name="get_chat_member (maxapi)",
            ok=True,
            detail=f"найден: user_id={m.user_id} name={m.first_name!r}",
        )
    except MaxApiError as e:
        return StepResult(
            name="get_chat_member (maxapi)",
            ok=False,
            detail=f"API {e.code} {_fmt_exc(e)}",
        )
    except Exception as e:
        return StepResult(name="get_chat_member (maxapi)", ok=False, detail=_fmt_exc(e))


async def approach_get_chat_members_filtered(bot, chat_id: int, user_id: int) -> StepResult:
    from maxapi.exceptions.max import MaxApiError

    try:
        page = await bot.get_chat_members(chat_id, user_ids=[user_id])
        n = len(page.members)
        if n == 0:
            return StepResult(
                name="get_chat_members(user_ids=[...])",
                ok=True,
                detail="0 участников в ответе (как get_chat_member None)",
            )
        u = page.members[0]
        return StepResult(
            name="get_chat_members(user_ids=[...])",
            ok=True,
            detail=f"1 участник: user_id={u.user_id} name={u.first_name!r}",
        )
    except MaxApiError as e:
        return StepResult(
            name="get_chat_members(user_ids=[...])",
            ok=False,
            detail=f"API {e.code} {_fmt_exc(e)}",
        )
    except Exception as e:
        return StepResult(
            name="get_chat_members(user_ids=[...])",
            ok=False,
            detail=_fmt_exc(e),
        )


async def approach_paginate_find_user(
    bot, chat_id: int, user_id: int, max_pages: int
) -> StepResult:
    from maxapi.exceptions.max import MaxApiError

    marker: int | None = None
    total_seen = 0
    try:
        for page_idx in range(max_pages):
            page = await bot.get_chat_members(chat_id, marker=marker, count=100)
            batch = len(page.members)
            total_seen += batch
            for m in page.members:
                if m.user_id == user_id:
                    return StepResult(
                        name=f"pagination (страница {page_idx + 1})",
                        ok=True,
                        detail=f"найден среди {total_seen} просмотренных: "
                        f"user_id={m.user_id} name={m.first_name!r}",
                    )
            marker = page.marker
            if marker is None:
                break
        return StepResult(
            name="pagination",
            ok=True,
            detail=f"user_id={user_id} не встречен в первых {max_pages} страницах "
            f"(просмотрено участников ~{total_seen})",
        )
    except MaxApiError as e:
        return StepResult(
            name="pagination",
            ok=False,
            detail=f"API {e.code} {_fmt_exc(e)}",
        )
    except Exception as e:
        return StepResult(name="pagination", ok=False, detail=_fmt_exc(e))


async def approach_app_helper(
    bot, chat_id: int, user_id: int, out: list[bool]
) -> StepResult:
    try:
        is_member = await user_is_channel_member_like_prod(bot, chat_id, user_id)
        out.append(is_member)
        return StepResult(
            name="user_is_channel_member (app)",
            ok=True,
            detail=f"результат: {is_member} (get_chat_member + при необходимости pagination)",
        )
    except Exception as e:
        return StepResult(
            name="user_is_channel_member (app)",
            ok=False,
            detail=_fmt_exc(e),
        )


def _print_result(r: StepResult) -> None:
    status = "OK  " if r.ok else "FAIL"
    print(f"  [{status}] {r.name}")
    print(f"         {r.detail}")


async def amain() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Тест методов MAX API для проверки подписки пользователя на канал."
    )
    parser.add_argument(
        "--chat-id",
        type=int,
        default=None,
        help="ID чата/канала в MAX (число из list_max_chats.py)",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="user_id пользователя MAX",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=30,
        help="Лимит страниц для теста pagination (по 100 участников)",
    )
    args = parser.parse_args()

    token = os.getenv("MAX_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        print("Ошибка: задайте MAX_BOT_TOKEN или BOT_TOKEN в .env", file=sys.stderr)
        return 1

    chat_id = args.chat_id
    user_id = args.user_id
    if chat_id is None or user_id is None:
        print(
            "Укажите --chat-id и --user-id (оба обязательны для проверки подписки).\n"
            "Пример: python test_subscription_check.py --chat-id -100123 --user-id 220372600",
            file=sys.stderr,
        )
        return 1

    from maxapi import Bot

    bot = Bot(token=token)
    try:
        print(f"chat_id={chat_id} user_id={user_id}\n")

        app_result: list[bool] = []
        steps = [
            await approach_get_chat_by_id(bot, chat_id),
            await approach_get_me_from_chat(bot, chat_id),
            await approach_get_chat_member(bot, chat_id, user_id),
            await approach_get_chat_members_filtered(bot, chat_id, user_id),
            await approach_paginate_find_user(bot, chat_id, user_id, args.max_pages),
            await approach_app_helper(bot, chat_id, user_id, app_result),
        ]

        for r in steps:
            _print_result(r)
            print()

        if app_result:
            print(
                "Итог (как в боте): user_is_channel_member =",
                app_result[0],
                "— это значение использует приложение (копия логики в этом файле).",
            )
        try:
            from app.services.channels import user_is_channel_member as from_app

            app_module_bool = await from_app(bot, chat_id, user_id)
            same = app_result and app_module_bool == app_result[0]
            print(
                "Сверка с app.services.channels.user_is_channel_member:",
                app_module_bool,
                "(совпадает)" if same else "(расхождение — проверьте код)",
            )
        except Exception as e:
            print(
                "Сверка с app.services.channels пропущена (нет зависимостей проекта):",
                f"{e.__class__.__name__}: {e}",
            )
        return 0
    finally:
        await bot.close_session()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
