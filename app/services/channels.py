from sqlalchemy import select, delete
from app.services.db import SessionLocal, Channel

async def get_all_channels():
    async with SessionLocal() as session:
        result = await session.execute(select(Channel))
        return result.scalars().all()

async def get_channel(channel_id: int):
    async with SessionLocal() as session:
        return await session.get(Channel, channel_id)

async def toggle_channel(channel_id: int):
    async with SessionLocal() as session:
        channel = await session.get(Channel, channel_id)
        if channel:
            channel.is_active = not channel.is_active
            await session.commit()
            return True
    return False

async def update_channel(channel_id: int, name: str = None, link: str = None):
    async with SessionLocal() as session:
        channel = await session.get(Channel, channel_id)
        if channel:
            if name is not None:
                channel.name = name
            if link is not None:
                # Validate link format
                if not link.startswith(('https://', 'http://', 't.me/')):
                    raise ValueError("Ссылка должна начинаться с https://, http:// или t.me/")
                channel.link = link
            await session.commit()
            return True
    return False

async def delete_channel(channel_id: int):
    async with SessionLocal() as session:
        channel = await session.get(Channel, channel_id)
        if channel:
            await session.delete(channel)
            await session.commit()
            return True
    return False

async def add_channel(channel_id: int, username: str, name: str = None, link: str = None):
    async with SessionLocal() as session:
        # Проверяем, нет ли уже канала с таким id
        existing = await session.get(Channel, channel_id)
        if existing:
            return False  # уже существует
            
        new_channel = Channel(
            id=channel_id,
            username=username,
            name=name or username,
            link=link or f"https://t.me/{username.lstrip('@')}",
            is_active=True
        )
        session.add(new_channel)
        await session.commit()
        return True