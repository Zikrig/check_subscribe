import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Токен бота MAX: https://dev.max.ru/docs/chatbots/bots-nocode/manage
    # Поддерживаются MAX_BOT_TOKEN и BOT_TOKEN (для обратной совместимости)
    BOT_TOKEN = os.getenv("MAX_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    ADMINS = [int(a.strip()) for a in os.getenv("ADMINS", "").split(",") if a]
    CHANNELS = []
    raw_channels = os.getenv("CHANNELS", "").split(",")
    for item in raw_channels:
        if not item.strip():
            continue
        chat_id, username = item.split(":")
        id = chat_id.strip()
        if not id.startswith("-"):
            id = "-" + id
        CHANNELS.append(
            {"id": int(id), "username": username.strip()}
        )

    DB_URL = (
        f"postgresql+asyncpg://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )

    SHEET_ID = os.getenv("SHEET_ID")


settings = Settings()
