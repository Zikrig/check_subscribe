from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.services.channels import get_all_channels
from app.services.membership import is_user_subscribed

async def subscription_keyboard(bot, user_id: int):
    buttons = []
    channels = await get_all_channels()
    
    for ch in channels:
        if not ch.is_active:
            continue

        subscribed = await is_user_subscribed(ch.id, user_id)

        emoji = "✅" if subscribed else "❌"
        display_name = ch.name or ch.username  # Используем name если есть, иначе username
        url = ch.link or f"https://max.ru/{ch.username.lstrip('@')}"
        text = f"{emoji} {display_name}"
        url_button = InlineKeyboardButton(text=text, url=url)
        buttons.append([url_button])

    check_button = InlineKeyboardButton(text="Я подписался", callback_data="check_subs")
    buttons.append([check_button])

    return InlineKeyboardMarkup(inline_keyboard=buttons)