"""Клавиатуры для MAX Bot API (inline keyboard)."""

from maxapi import Bot
from maxapi.types import CallbackButton, LinkButton
from maxapi.types.attachments.attachment import Attachment
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.config import settings
from app.services.channels import (
    get_all_channels,
    resolve_channel_url,
    user_is_channel_member,
)


async def subscription_keyboard(bot: Bot, user_id: int) -> Attachment:
    """Собирает inline-клавиатуру: ссылки на каналы + проверка подписки."""
    builder = InlineKeyboardBuilder()
    channels = await get_all_channels()

    for ch in channels:
        if not ch.is_active:
            continue

        subscribed = await user_is_channel_member(bot, ch.id, user_id)

        emoji = "✅" if subscribed else "❌"
        display_name = ch.name or ch.username
        url = await resolve_channel_url(bot, ch)
        builder.row(LinkButton(text=f"{emoji} {display_name}", url=url))

    builder.row(CallbackButton(text="Я подписался", payload="check_subs"))
    return builder.as_markup()
