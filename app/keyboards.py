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
        text = f"{emoji} {ch.username}"
        url_button = InlineKeyboardButton(text=text, url=f"https://t.me/{ch.username.lstrip('@')}")
        buttons.append([url_button])

    check_button = InlineKeyboardButton(text="Я подписался", callback_data="check_subs")
    buttons.append([check_button])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
