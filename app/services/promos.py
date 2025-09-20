from sqlalchemy import select
from app.services.db import SessionLocal, Promo
from app.services.counters import increment_counter

async def get_or_assign_promo(user_id: int) -> str | None:
    async with SessionLocal() as session:
        # Проверяем, есть ли уже выданный промокод
        result = await session.execute(select(Promo).where(Promo.user_id == user_id))
        promo = result.scalar_one_or_none()
        if promo:
            promo.user_id = user_id
            await session.commit()
            return promo.code

        # Берём первый свободный
        result = await session.execute(select(Promo).where(Promo.user_id.is_(None)).limit(1))
        promo = result.scalar_one_or_none()
        if not promo:
            return None

        promo.user_id = user_id
        await increment_counter() 
        await session.commit()
        return promo.code
