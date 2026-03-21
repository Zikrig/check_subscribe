# app/handlers/user — MAX Bot API

from maxapi import F, Router
from maxapi.enums.parse_mode import ParseMode
from maxapi.filters.command import Command
from maxapi.types import MessageCallback, MessageCreated

from app.config import settings
from app.keyboards import subscription_keyboard
from app.services.channels import get_all_channels
from app.services.promos import get_or_assign_promo
from app.services.replics import get_replic

router = Router("user")


@router.message_created(Command("start"))
async def start_handler(event: MessageCreated):
    if not event.message.sender:
        return

    user_id = event.message.sender.user_id
    bot = event._ensure_bot()
    kb = await subscription_keyboard(bot, user_id)
    start_text = await get_replic("start_message")
    await event.message.answer(text=start_text, attachments=[kb])

    if user_id in settings.ADMINS:
        await event.message.answer(
            "Привет, админ! Используй /info для списка команд."
        )


@router.message_callback(F.callback.payload == "check_subs")
async def check_subs_callback(event: MessageCallback):
    user_id = event.callback.user.user_id
    bot = event._ensure_bot()
    kb = await subscription_keyboard(bot, user_id)

    all_subscribed = True
    channels = await get_all_channels()

    for ch in channels:
        if not ch.is_active:
            continue
        try:
            member = await bot.get_chat_member(ch.id, user_id)
            if member is None:
                all_subscribed = False
                break
        except Exception:
            all_subscribed = False
            break

    if not event.message or not event.message.body:
        await event.answer(notification="Сообщение недоступно")
        return

    if all_subscribed:
        promo = await get_or_assign_promo(user_id)
        success_text = await get_replic("success_message")
        await event.message.edit(
            text=success_text.format(promo=promo or ""),
            attachments=[],
            parse_mode=ParseMode.HTML,
        )
    else:
        not_subbed_text = await get_replic("not_subbed_message")
        await event.message.edit(
            text=not_subbed_text,
            attachments=[kb],
            parse_mode=ParseMode.HTML,
        )

    await event.answer()
