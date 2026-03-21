# bot.py — MAX Messenger (см. https://dev.max.ru/docs/chatbots/bots-coding/prepare)

import asyncio
import logging

from maxapi import Bot, Dispatcher

from app.config import settings
from app.handlers import admin, user
from app.services.channels import log_channels_at_startup
from app.services.db import init_db
from app.services.sheets import periodic_update

logging.basicConfig(level=logging.INFO)


async def main():
    if not settings.BOT_TOKEN:
        raise RuntimeError(
            "Задайте MAX_BOT_TOKEN или BOT_TOKEN в .env (токен из кабинета бота MAX)."
        )

    await init_db()
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_routers(admin.router, user.router)

    await log_channels_at_startup(bot)

    asyncio.create_task(periodic_update())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
