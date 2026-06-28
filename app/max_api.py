"""Настройка base URL MAX Bot API (миграция на platform-api2.max.ru)."""

from __future__ import annotations

from typing import Any

from app.config import settings


def apply_max_api_url(bot: Any) -> None:
    """Переключить maxapi с platform-api.max.ru на platform-api2.max.ru."""
    bot.set_api_url(settings.MAX_API_URL)
