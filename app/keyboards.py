"""Клавиатуры для MAX Bot API (inline keyboard)."""

from maxapi import Bot
from maxapi.types import CallbackButton, LinkButton
from maxapi.types.attachments.attachment import Attachment
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.config import settings
from app.services.channels import get_all_channels, resolve_channel_url


async def subscription_keyboard(bot: Bot, _user_id: int) -> Attachment:
    """Собирает inline-клавиатуру: по одной ссылке на канал (текст кнопки = URL)."""
    builder = InlineKeyboardBuilder()
    channels = await get_all_channels()

    for ch in channels:
        if not ch.is_active:
            continue

        url = await resolve_channel_url(bot, ch)
        builder.row(LinkButton(text=url, url=url))

    builder.row(CallbackButton(text="Я подписался", payload="check_subs"))
    return builder.as_markup()
