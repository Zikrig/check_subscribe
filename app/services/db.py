# app/db — модели данных (канал); инициализация JSON-хранилища

from dataclasses import dataclass

from app.services.storage import init_storage


@dataclass
class Channel:
    id: int
    username: str
    name: str | None = None
    link: str | None = None
    is_active: bool = True


async def init_db():
    await init_storage()
