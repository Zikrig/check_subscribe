"""Публичная ссылка на бота MAX для кнопки «Поделиться»."""

from __future__ import annotations

from maxapi import Bot

from app.config import settings


def _nick_for_max_url(username: str) -> str:
    return username.strip().lstrip("@")


async def get_bot_share_url(bot: Bot) -> str | None:
    """https://max.ru/ник или BOT_SHARE_URL из .env."""
    override = getattr(settings, "BOT_SHARE_URL", None)
    if override:
        return override
    try:
        me = await bot.get_me()
        if me.username:
            return f"https://max.ru/{_nick_for_max_url(me.username)}"
    except Exception:
        pass
    return None
