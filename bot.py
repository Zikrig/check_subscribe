# bot.py

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from app.config import settings
from app.handlers import user, admin
from app.services.sheets import periodic_update
from app.services.db import init_db

async def main():
    await init_db()
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(user.router)
    dp.include_router(admin.router)

    asyncio.create_task(periodic_update())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())