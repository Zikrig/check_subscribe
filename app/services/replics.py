# /app/replics.py

from sqlalchemy import select
from app.services.db import SessionLocal, Replic

async def get_replic(name: str) -> str:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Replic).where(Replic.name == name)
        )
        replic = result.scalar_one_or_none()
        if replic:
            return replic.text
        
        # Fallback to default values if not found in DB
        default_replics = {
            "start_message": "Привет! Подпишись на наши каналы:",
            "success_message": "Все подписки выполнены!\nТвой промокод: <code>{promo}</code>",
            "not_subbed_message": "Похоже, ты ещё не подписан на все каналы. Проверь и нажми кнопку снова."
        }
        return default_replics.get(name, "")