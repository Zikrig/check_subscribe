from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.config import settings
from app.services.channels import get_all_channels

async def subscription_keyboard(bot, user_id: int):
    buttons = []
    channels = await get_all_channels()
    
    for ch in channels:
        if not ch.is_active:
            continue
            
        try:
            member = await bot.get_chat_member(ch.id, user_id)
            subscribed = member.status in ["member", "administrator", "creator"]
        except:
            subscribed = False

        emoji = "✅" if subscribed else "❌"
        display_name = ch.name or ch.username  # Используем name если есть, иначе username
        url = ch.link or f"https://t.me/{ch.username.lstrip('@')}"  # Используем link если есть
        text = f"{emoji} {display_name}"
        url_button = InlineKeyboardButton(text=text, url=url)
        buttons.append([url_button])

    check_button = InlineKeyboardButton(text="Я подписался", callback_data="check_subs")
    buttons.append([check_button])

    return InlineKeyboardMarkup(inline_keyboard=buttons)