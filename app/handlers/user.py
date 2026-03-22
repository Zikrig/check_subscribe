# app/handlers/user — MAX Bot API

import html
import logging

from maxapi import F, Router
from maxapi.enums.parse_mode import ParseMode
from maxapi.filters.command import Command
from maxapi.types import LinkButton, MessageCallback, MessageCreated
from maxapi.types.input_media import InputMedia
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.types.updates.bot_started import BotStarted

from app.callback_ack import send_callback_ack
from app.config import settings
from app.keyboards import subscription_keyboard
from app.services.bot_link import get_bot_share_url
from app.services.bot_started_description import (
    resolve_bot_started_description_image_path,
)
from app.services.channels import get_all_channels, user_is_channel_member
from app.services.promos import get_or_assign_promo
from app.services.replics import get_replic
from app.services.promo_followup import (
    get_promo_followup_button_url,
    resolve_promo_followup_image_path,
)
from app.services.start_image import resolve_start_image_path

logger = logging.getLogger(__name__)

# Сообщение перед блоком «акция» (картинка/текст из админки)
PROMO_BEFORE_FOLLOWUP_TEXT = (
    "Не забудь воспользоваться приятной акцией для моих подписчиков."
)

router = Router("user")


async def _start_attachments(kb):
    """Картинка (store или START_IMAGE_PATH) + inline-клавиатура."""
    out = []
    p = await resolve_start_image_path()
    if p is not None:
        out.append(InputMedia(str(p)))
    elif settings.START_IMAGE_PATH is not None:
        logger.warning("START_IMAGE_PATH задан, но файл не найден: %s", settings.START_IMAGE_PATH)
    out.append(kb)
    return out


async def _main_menu_text_and_keyboard(bot, user_id: int):
    kb = await subscription_keyboard(bot, user_id)
    start_text = await get_replic("start_message")
    return start_text, kb


async def _send_main_menu_answer(message, bot, user_id: int) -> None:
    start_text, kb = await _main_menu_text_and_keyboard(bot, user_id)
    await message.answer(text=start_text, attachments=await _start_attachments(kb))


async def _send_bot_started_description_if_any(bot, chat_id: int) -> None:
    """Первое сообщение только для события bot_started (кнопка «Начало»)."""
    cap = (await get_replic("bot_started_description")).strip()
    img_path = await resolve_bot_started_description_image_path()
    if img_path is not None:
        text = cap if cap else "\u200b"
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            attachments=[InputMedia(str(img_path))],
            parse_mode=ParseMode.HTML if cap else None,
        )
    elif cap:
        await bot.send_message(
            chat_id=chat_id,
            text=cap,
            parse_mode=ParseMode.HTML,
        )


async def send_start_response(event: MessageCreated) -> None:
    if not event.message.sender:
        return

    user_id = event.message.sender.user_id
    bot = event._ensure_bot()
    await _send_main_menu_answer(event.message, bot, user_id)

    if user_id in settings.ADMINS:
        await event.message.answer(
            "Привет, админ! Используй /info для списка команд."
        )


@router.bot_started()
async def bot_started_handler(event: BotStarted) -> None:
    """Кнопка «Начало» в MAX шлёт bot_started, а не /start."""
    bot = event._ensure_bot()
    user_id = event.user.user_id
    await _send_bot_started_description_if_any(bot, event.chat_id)
    start_text, kb = await _main_menu_text_and_keyboard(bot, user_id)
    await bot.send_message(
        chat_id=event.chat_id,
        text=start_text,
        attachments=await _start_attachments(kb),
    )
    if user_id in settings.ADMINS:
        await bot.send_message(
            chat_id=event.chat_id,
            text="Привет, админ! Используй /info для списка команд.",
        )


@router.message_created(Command("start"))
async def start_handler(event: MessageCreated):
    await send_start_response(event)


@router.message_created()
async def any_text_message_as_start(event: MessageCreated):
    """Всё, что не обработал admin-роутер (команды, FSM), — как /start."""
    await send_start_response(event)


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
        if not await user_is_channel_member(bot, ch.id, user_id):
            all_subscribed = False
            break

    if not event.message or not event.message.body:
        await send_callback_ack(
            bot, event.callback.callback_id, notification="Сообщение недоступно"
        )
        return

    if all_subscribed:
        promo = await get_or_assign_promo(user_id)
        success_text = await get_replic("success_message")
        if "{promo}" in success_text:
            intro = success_text.replace("{promo}", "").strip()
        else:
            intro = success_text
        await event.message.edit(
            text=intro,
            attachments=[],
            parse_mode=ParseMode.HTML,
        )
        if promo:
            promo_attachments = []
            share_url = await get_bot_share_url(bot)
            if share_url:
                share_kb = InlineKeyboardBuilder()
                share_kb.row(
                    LinkButton(text="Поделиться ботом", url=share_url)
                )
                promo_attachments = [share_kb.as_markup()]

            await event.message.answer(
                text=f"<code>{html.escape(promo)}</code>",
                parse_mode=ParseMode.HTML,
                attachments=promo_attachments,
            )
            cap = (await get_replic("promo_followup_message")).strip()
            img_path = await resolve_promo_followup_image_path()
            link_url = await get_promo_followup_button_url()
            btn_text = (await get_replic("promo_followup_link_button_text")).strip() or "Перейти"

            if img_path is not None or cap or link_url:
                await event.message.answer(
                    text=PROMO_BEFORE_FOLLOWUP_TEXT,
                    parse_mode=ParseMode.HTML,
                )
            if img_path is not None:
                text = cap if cap else "\u200b"
                att = [InputMedia(str(img_path))]
                if link_url:
                    link_kb = InlineKeyboardBuilder()
                    link_kb.row(LinkButton(text=btn_text, url=link_url))
                    att.append(link_kb.as_markup())
                await event.message.answer(
                    text=text,
                    attachments=att,
                    parse_mode=ParseMode.HTML if cap else None,
                )
            elif cap:
                att = []
                if link_url:
                    link_kb = InlineKeyboardBuilder()
                    link_kb.row(LinkButton(text=btn_text, url=link_url))
                    att.append(link_kb.as_markup())
                await event.message.answer(
                    text=cap,
                    parse_mode=ParseMode.HTML,
                    attachments=att,
                )
            elif link_url:
                link_kb = InlineKeyboardBuilder()
                link_kb.row(LinkButton(text=btn_text, url=link_url))
                await event.message.answer(
                    text="\u200b",
                    attachments=[link_kb.as_markup()],
                )
    else:
        not_subbed_text = await get_replic("not_subbed_message")
        await event.message.edit(
            text=not_subbed_text,
            attachments=[kb],
            parse_mode=ParseMode.HTML,
        )

    await send_callback_ack(bot, event.callback.callback_id)
