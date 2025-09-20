from sqlalchemy import select, update
from app.services.db import SessionLocal, Counter

async def increment_counter(name: str = "promos_issued"):
    async with SessionLocal() as session:
        counter = await session.get(Counter, name)
        if counter:
            counter.value += 1
        else:
            counter = Counter(name=name, value=1)
            session.add(counter)
        await session.commit()
        return counter.value

async def get_counter(name: str = "promos_issued"):
    async with SessionLocal() as session:
        counter = await session.get(Counter, name)
        return counter.value if counter else 0

async def reset_counter(name: str = "promos_issued"):
    async with SessionLocal() as session:
        counter = await session.get(Counter, name)
        if counter:
            counter.value = 0
            await session.commit()
        return 0