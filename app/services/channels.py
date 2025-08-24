from sqlalchemy import select, update
from app.services.db import SessionLocal, Channel

async def get_all_channels():
    async with SessionLocal() as session:
        result = await session.execute(select(Channel))
        return result.scalars().all()

async def toggle_channel(channel_id: int):
    async with SessionLocal() as session:
        channel = await session.get(Channel, channel_id)
        if channel:
            channel.is_active = not channel.is_active
            await session.commit()
            return True
    return False