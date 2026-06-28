import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    MAX_API_URL = (
        os.getenv("MAX_API_URL", "https://platform-api2.max.ru").strip().rstrip("/")
    )
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMINS = [int(a.strip()) for a in os.getenv("ADMINS", "").split(",") if a]
    CHANNELS = []
    raw_channels = os.getenv("CHANNELS", "").split(",")
    for item in raw_channels:
        chat_id, username = item.split(":")
        CHANNELS.append({"id": int(chat_id), "username": username})

    SQLITE_PATH = os.getenv("SQLITE_PATH", "data/promos.db")
    DB_URL = f"sqlite+aiosqlite:///{SQLITE_PATH}"
    
    SHEET_ID = os.getenv("SHEET_ID")
    
settings = Settings()
