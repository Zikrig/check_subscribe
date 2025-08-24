# app/handlers/user

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from app.keyboards import subscription_keyboard
from app.services.promos import get_or_assign_promo
from app.config import settings
from app.services.replics import get_replic
from app.services.channels import get_all_channels

router = Router()

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
            
        try:
            member = await callback.bot.get_chat_member(ch.id, callback.from_user.id)
            if member.status not in ["member", "administrator", "creator"]:
                all_subscribed = False
        except:
            all_subscribed = False
            

    if all_subscribed:
        promo = await get_or_assign_promo(callback.from_user.id)
        success_text = await get_replic("success_message")
        await callback.message.edit_text(
            success_text.format(promo=promo), 
            parse_mode="HTML"
        )
    else:
        not_subbed_text = await get_replic("not_subbed_message")
        await callback.message.edit_text(not_subbed_text, reply_markup=kb)

    await callback.answer()
    


