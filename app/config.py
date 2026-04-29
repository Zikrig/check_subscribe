import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _resolve_data_json_path() -> Path:
    raw = os.getenv("DATA_JSON_PATH", "data/store.json")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _resolve_optional_path(env_name: str) -> Path | None:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


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
        # if not id.startswith("-"):
        #     id = "-" + id
        CHANNELS.append(
            {"id": int(id), "username": username.strip()}
        )

    # Один JSON-файл вместо PostgreSQL (см. app.services.storage)
    DATA_JSON_PATH = _resolve_data_json_path()

    # Приветственная картинка для /start и кнопки «Начало» (локальный файл)
    START_IMAGE_PATH = _resolve_optional_path("START_IMAGE_PATH")

    SHEET_ID = os.getenv("SHEET_ID")

    # Webhook-режим
    WEBHOOK_PUBLIC_URL = os.getenv("WEBHOOK_PUBLIC_URL", "").strip() or None
    WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip() or None
    WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))


settings = Settings()
