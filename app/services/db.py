# app/db — тип строки канала в JSON-хранилище; инициализация без БД.

from typing import TypedDict

from app.services.storage import init_storage


class Channel(TypedDict):
    """Одна запись из store['channels'][str id] — только dict-поля JSON."""

    id: int
    username: str
    name: str | None
    link: str | None
    is_active: bool


async def init_db():
    await init_storage()
