"""Клавиатуры для MAX Bot API (inline keyboard)."""

from maxapi import Bot
from maxapi.types import CallbackButton, LinkButton
from maxapi.types.attachments.attachment import Attachment
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.config import settings
from app.services.channels import get_all_channels


async def subscription_keyboard(bot: Bot, user_id: int) -> Attachment:
    """Собирает inline-клавиатуру: ссылки на каналы + проверка подписки."""
    builder = InlineKeyboardBuilder()
    channels = await get_all_channels()

    for ch in channels:
        if not ch.is_active:
            continue

        try:
            member = await bot.get_chat_member(ch.id, user_id)
            subscribed = member is not None
        except Exception:
            subscribed = False

        emoji = "✅" if subscribed else "❌"
        display_name = ch.name or ch.username
        url = ch.link or f"https://max.ru/{ch.username.lstrip('@')}"
        builder.row(LinkButton(text=f"{emoji} {display_name}", url=url))

    builder.row(CallbackButton(text="Я подписался", payload="check_subs"))
    return builder.as_markup()
