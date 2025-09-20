# app/db
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, Mapped, mapped_column
from sqlalchemy import String, BigInteger, insert, select

from app.config import settings

engine = create_async_engine(settings.DB_URL, echo=False)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class Promo(Base):
    __tablename__ = "promos"
    code: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

class Replic(Base):
    __tablename__ = "replics"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    text: Mapped[str] = mapped_column(String)

class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String, nullable=True)  # Новое поле
    link: Mapped[str] = mapped_column(String, nullable=True)  # Новое поле
    is_active: Mapped[bool] = mapped_column(default=True)

class Counter(Base):
    __tablename__ = "counters"
    name: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[int] = mapped_column(default=0)
    
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Добавляем счетчик если его нет
        exists = await conn.execute(
            select(Counter).where(Counter.name == "promos_issued")
        )
        if not exists.scalar_one_or_none():
            await conn.execute(
                insert(Counter).values(name="promos_issued", value=0)
            )
            
        # Добавляем каналы из конфига если их нет
        for channel in settings.CHANNELS:
            exists = await conn.execute(
                select(Channel).where(Channel.id == channel["id"])
            )
            if not exists.scalar_one_or_none():
                await conn.execute(
                    insert(Channel).values(
                        id=channel["id"],
                        username=channel["username"],
                        name=channel["username"],  # По умолчанию используем username как name
                        is_active=True
                    )
                )
        await conn.commit()