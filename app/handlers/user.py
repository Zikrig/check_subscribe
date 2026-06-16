# app/handlers/user

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from app.keyboards import subscription_keyboard
from app.services.promos import get_or_assign_promo
from app.config import settings
from app.services.replics import get_replic
from app.services.channels import get_all_channels
from app.services.membership import is_user_subscribed

router = Router()


async def _safe_edit_text(message, text: str, **kwargs):
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise

@router.message(F.text == "/start")
async def start_handler(message: Message):
    kb = await subscription_keyboard(message.bot, message.from_user.id)
    start_text = await get_replic("start_message")
    await message.answer(start_text, reply_markup=kb)
    if message.from_user.id in settings.ADMINS:
        await message.answer("Привет, админ! Используй /info для списка команд.")

@router.callback_query(F.data == "check_subs")
async def check_subs_callback(callback: CallbackQuery):
    kb = await subscription_keyboard(callback.bot, callback.from_user.id)
    
    all_subscribed = True
    channels = await get_all_channels()
    
    for ch in channels:
        if not ch.is_active:
            continue

        if not await is_user_subscribed(ch.id, callback.from_user.id):
            all_subscribed = False
            

    if all_subscribed:
        promo = await get_or_assign_promo(callback.from_user.id)
        success_text = await get_replic("success_message")
        await _safe_edit_text(
            callback.message,
            success_text.format(promo=promo),
            parse_mode="HTML",
        )
    else:
        not_subbed_text = await get_replic("not_subbed_message")
        await _safe_edit_text(callback.message, not_subbed_text, reply_markup=kb)

    await callback.answer()
    


