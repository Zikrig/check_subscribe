"""
Тестовый скрипт: список групповых чатов/каналов, где состоит бот MAX.

Запуск из корня проекта:
  pip install maxapi python-dotenv
  python list_max_chats.py

Токен: MAX_BOT_TOKEN или BOT_TOKEN в .env (как в app/config.py).
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()
    token = os.getenv("MAX_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        print("Ошибка: задайте MAX_BOT_TOKEN или BOT_TOKEN в .env", file=sys.stderr)
        sys.exit(1)

    from maxapi import Bot

    bot = Bot(token=token)
    try:
        marker: int | None = None
        n = 0
        print(
            "chat_id\ttype\ttitle\tlink\tparticipants"
        )
        print("-" * 80)

        while True:
            page = await bot.get_chats(count=100, marker=marker)
            for chat in page.chats:
                n += 1
                title = (chat.title or "").replace("\t", " ")
                link = (chat.link or "").replace("\t", " ")
                print(
                    f"{chat.chat_id}\t{chat.type}\t{title}\t{link}\t"
                    f"{chat.participants_count}"
                )

            marker = page.marker
            if marker is None:
                break

        print("-" * 80)
        print(f"Всего записей: {n}")
    finally:
        await bot.close_session()


if __name__ == "__main__":
    asyncio.run(main())
