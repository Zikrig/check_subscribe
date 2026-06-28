# bot.py — MAX Messenger (см. https://dev.max.ru/docs/chatbots/bots-coding/prepare)

import asyncio
import logging

from maxapi import Bot, Dispatcher
from maxapi.enums.update import UpdateType

from app.config import settings
from app.max_api import apply_max_api_url
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
    apply_max_api_url(bot)
    dp = Dispatcher()
    dp.include_routers(admin.router, user.router)

    await log_channels_at_startup(bot)

    asyncio.create_task(periodic_update())
    if not settings.WEBHOOK_PUBLIC_URL:
        raise RuntimeError(
            "Задайте WEBHOOK_PUBLIC_URL в .env для запуска в режиме webhook."
        )

    await bot.subscribe_webhook(
        url=settings.WEBHOOK_PUBLIC_URL,
        update_types=[
            UpdateType.MESSAGE_CREATED,
            UpdateType.MESSAGE_CALLBACK,
            UpdateType.BOT_STARTED,
            UpdateType.USER_ADDED,
        ],
        secret=settings.WEBHOOK_SECRET,
    )
    await dp.handle_webhook(
        bot,
        host=settings.WEBHOOK_HOST,
        port=settings.WEBHOOK_PORT,
        path=settings.WEBHOOK_PATH,
        secret=settings.WEBHOOK_SECRET,
    )


if __name__ == "__main__":
    asyncio.run(main())
