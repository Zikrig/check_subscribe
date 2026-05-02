# app/handlers/admin — MAX Bot API

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.context.state_machine import State, StatesGroup
from maxapi.filters.command import Command
from maxapi.types import CallbackButton, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.callback_ack import send_callback_ack
from app.config import settings
from app.services.channels import (
    add_channel,
    delete_channel,
    get_all_channels,
    get_channel,
    parse_admin_channel_input,
    toggle_channel,
    update_channel,
)
from app.services.counters import get_counter, reset_counter
from app.services.replics import get_replic
from app.services.bot_started_description import (
    delete_stored_bot_started_description_image,
    has_stored_bot_started_description_image,
    replace_stored_bot_started_description_image,
)
from app.services.promo_followup import (
    clear_promo_followup_button_url,
    delete_stored_promo_followup_image,
    has_stored_promo_followup_image,
    normalize_promo_followup_button_url,
    replace_stored_promo_followup_image,
)
from app.services.start_image import (
    delete_stored_start_image,
    first_image_url_from_message_body,
    has_stored_start_image,
    replace_stored_start_image,
)
from app.services.storage import mutate_store, read_store
from app.services.sheets import update_table

router = Router("admin")


async def _ack_callback(
    event: MessageCallback, *, notification: str | None = None
) -> None:
    """Подтвердить callback без повторной отправки старых attachments (иначе затирается message.edit)."""
    bot = event._ensure_bot()
    await send_callback_ack(
        bot, event.callback.callback_id, notification=notification
    )


INFO_TEXT = (
    "/start — версия для пользователей\n"
    "/info — список команд\n"
    "/table — обновить таблицу\n"
    "/channels — управление каналами\n"
    "/edit_replics — редактировать реплики\n"
    "/stats — статистика выданных промокодов"
)


class EditReplic(StatesGroup):
    choosing_replic = State()
    editing_text = State()


class EditStartImage(StatesGroup):
    menu = State()
    waiting_photo = State()


class EditPromoFollowup(StatesGroup):
    menu = State()
    waiting_photo = State()
    editing_text = State()
    editing_link = State()
    editing_button_label = State()


class EditBotStartedDesc(StatesGroup):
    menu = State()
    waiting_photo = State()
    editing_text = State()


class ChannelManage(StatesGroup):
    choosing_action = State()
    adding_channel = State()
    editing_name = State()
    editing_link = State()
    confirming_delete = State()


def _after_prefix(prefix: str, payload: str) -> str:
    if not payload.startswith(prefix):
        return ""
    return payload[len(prefix) :]


@router.message_created(Command("table"))
async def cmd_table(event: MessageCreated):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    await update_table()
    await event.message.answer("Таблица актуализирована!")


@router.message_created(Command("info"))
async def cmd_info(event: MessageCreated):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    await event.message.answer(INFO_TEXT)


def _edit_replics_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Описание", payload="edit_bot_started_desc"))
    kb.row(
        CallbackButton(text="Стартовое сообщение", payload="edit_start")
    )
    kb.row(
        CallbackButton(text="Стартовая картинка", payload="edit_start_image")
    )
    kb.row(
        CallbackButton(text="Сообщение об успехе", payload="edit_success")
    )
    kb.row(
        CallbackButton(
            text="Сообщение об акции (после промокода)",
            payload="edit_promo_followup",
        )
    )
    kb.row(
        CallbackButton(text="Сообщение о неподписке", payload="edit_not_subbed"),
    )
    kb.row(CallbackButton(text="Назад", payload="cancel_edit"))
    return kb


async def _start_image_menu_text() -> str:
    has_st = await has_stored_start_image()
    has_env = (
        settings.START_IMAGE_PATH is not None
        and settings.START_IMAGE_PATH.is_file()
    )
    lines = [
        "Стартовая картинка — главный экран с меню (после «Описание», если оно задано для кнопки «Начало»).",
        "",
    ]
    if has_st:
        lines.append("Сейчас: файл, загруженный через бота (в каталоге data).")
    elif has_env:
        lines.append(
            f"Сейчас: START_IMAGE_PATH ({settings.START_IMAGE_PATH})."
        )
    else:
        lines.append("Сейчас: картинка не задана.")
    lines.append("")
    lines.append(
        "Загрузка через бота сохраняет файл в data и имеет приоритет над START_IMAGE_PATH."
    )
    return "\n".join(lines)


def _start_image_menu_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="Загрузить новое фото", payload="start_img_upload")
    )
    kb.row(
        CallbackButton(text="Удалить файл из бота", payload="start_img_delete")
    )
    kb.row(CallbackButton(text="Назад", payload="start_img_back"))
    return kb


def _start_image_wait_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload="start_img_cancel"))
    return kb


@router.message_created(Command("edit_replics"))
async def cmd_edit_replics(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return

    kb = _edit_replics_keyboard()

    await event.message.answer(
        "Выберите реплику для редактирования:",
        attachments=[kb.as_markup()],
    )
    await context.set_state(EditReplic.choosing_replic)


@router.message_callback(EditReplic.choosing_replic, F.callback.payload == "cancel_edit")
async def choose_replic_cancel(event: MessageCallback, context: MemoryContext):
    await context.clear()
    if event.message:
        await event.message.edit(text="Редактирование отменено.", attachments=[])
        await event.message.answer(INFO_TEXT)
    await _ack_callback(event)


async def _promo_followup_menu_text() -> str:
    has_img = await has_stored_promo_followup_image()
    text = await get_replic("promo_followup_message")
    text_preview = text.strip() if text else "(пусто)"
    data = await read_store()
    raw_link = (data.get("promo_followup_button_url") or "").strip()
    link_preview = raw_link if raw_link else "(не задана)"
    lines = [
        "Сообщение об акции: третье сообщение после промокода.",
        "",
        f"Картинка: {'загружена' if has_img else 'не задана'}.",
        f"Текст: {text_preview}",
        f"Ссылка кнопки под акцией: {link_preview}",
        "",
        "Без текста и без картинки блок не отправляется, если не задана ссылка кнопки.",
    ]
    return "\n".join(lines)


def _promo_followup_menu_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Текст сообщения", payload="promo_fw_text"))
    kb.row(
        CallbackButton(text="Загрузить / заменить фото", payload="promo_fw_upload")
    )
    kb.row(CallbackButton(text="Удалить картинку", payload="promo_fw_delete"))
    kb.row(
        CallbackButton(
            text="Ссылка кнопки под акцией", payload="promo_fw_link"
        )
    )
    kb.row(
        CallbackButton(text="Удалить ссылку кнопки", payload="promo_fw_link_delete")
    )
    kb.row(
        CallbackButton(text="Текст кнопки ссылки", payload="promo_fw_btn_label")
    )
    kb.row(CallbackButton(text="Назад", payload="promo_fw_back"))
    return kb


def _promo_followup_wait_keyboard() -> InlineKeyboardBuilder:
    """Кнопка без видимого текста + отмена (при ожидании фото)."""
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="Без картинки", payload="promo_fw_nop"),
        CallbackButton(text="❌ Отменить", payload="promo_fw_cancel"),
    )
    return kb


async def _bot_started_desc_menu_text() -> str:
    has_img = await has_stored_bot_started_description_image()
    text = await get_replic("bot_started_description")
    text_preview = text.strip() if text else "(пусто)"
    lines = [
        "Описание: первое сообщение при нажатии кнопки «Начало» (не при /start).",
        "Дальше — стартовое сообщение и меню.",
        "",
        f"Картинка: {'загружена' if has_img else 'не задана'}.",
        f"Текст: {text_preview}",
        "",
        "Без текста и без картинки блок не отправляется.",
    ]
    return "\n".join(lines)


def _bot_started_desc_menu_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Текст", payload="bsd_text"))
    kb.row(CallbackButton(text="Загрузить / заменить фото", payload="bsd_upload"))
    kb.row(CallbackButton(text="Удалить картинку", payload="bsd_delete"))
    kb.row(CallbackButton(text="Назад", payload="bsd_back"))
    return kb


def _bot_started_desc_wait_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="Без картинки", payload="bsd_nop"),
        CallbackButton(text="❌ Отменить", payload="bsd_cancel"),
    )
    return kb


@router.message_callback(EditReplic.choosing_replic, F.callback.payload == "edit_bot_started_desc")
async def open_bot_started_desc_menu(event: MessageCallback, context: MemoryContext):
    text = await _bot_started_desc_menu_text()
    await context.set_state(EditBotStartedDesc.menu)
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_bot_started_desc_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditReplic.choosing_replic, F.callback.payload == "edit_promo_followup")
async def open_promo_followup_menu(event: MessageCallback, context: MemoryContext):
    text = await _promo_followup_menu_text()
    await context.set_state(EditPromoFollowup.menu)
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_promo_followup_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditReplic.choosing_replic, F.callback.payload == "edit_start_image")
async def open_start_image_menu(event: MessageCallback, context: MemoryContext):
    text = await _start_image_menu_text()
    await context.set_state(EditStartImage.menu)
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_start_image_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditReplic.choosing_replic)
async def choose_replic(event: MessageCallback, context: MemoryContext):
    payload = event.callback.payload or ""
    replic_map = {
        "edit_start": "start_message",
        "edit_success": "success_message",
        "edit_not_subbed": "not_subbed_message",
    }
    replic_name = replic_map.get(payload)
    if not replic_name:
        await _ack_callback(event)
        return

    current_text = await get_replic(replic_name)
    await context.update_data(replic_name=replic_name)

    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload="cancel_edit"))

    if event.message:
        await event.message.edit(
            text=f"Текущий текст: {current_text}\n\nОтправьте новый текст:",
            attachments=[kb.as_markup()],
        )
    await context.set_state(EditReplic.editing_text)
    await _ack_callback(event)


@router.message_callback(EditReplic.editing_text, F.callback.payload == "cancel_edit")
async def cancel_edit_replic(event: MessageCallback, context: MemoryContext):
    await context.clear()
    if event.message:
        await event.message.edit(text="Редактирование отменено.", attachments=[])
        await event.message.answer(INFO_TEXT)
    await _ack_callback(event)


@router.message_created(EditReplic.editing_text)
async def save_new_replic(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    if not event.message.body or not event.message.body.text:
        return

    data = await context.get_data()
    replic_name = data.get("replic_name")
    if not replic_name:
        return

    new_text = event.message.body.text

    def _save_replic(data):
        data.setdefault("replics", {})[replic_name] = new_text

    await mutate_store(_save_replic)

    await event.message.answer("Реплика успешно обновлена!")
    await context.clear()
    await event.message.answer(INFO_TEXT)


@router.message_callback(EditStartImage.menu, F.callback.payload == "start_img_back")
async def start_image_back_to_replics(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditReplic.choosing_replic)
    if event.message:
        await event.message.edit(
            text="Выберите реплику для редактирования:",
            attachments=[_edit_replics_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditStartImage.menu, F.callback.payload == "start_img_upload")
async def start_image_begin_upload(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditStartImage.waiting_photo)
    if event.message:
        await event.message.edit(
            text="Отправьте изображение (фото).",
            attachments=[_start_image_wait_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditStartImage.menu, F.callback.payload == "start_img_delete")
async def start_image_delete_stored(event: MessageCallback, context: MemoryContext):
    await delete_stored_start_image()
    text = await _start_image_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_start_image_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditStartImage.waiting_photo, F.callback.payload == "start_img_cancel")
async def start_image_cancel_upload(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditStartImage.menu)
    text = await _start_image_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_start_image_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_created(EditStartImage.waiting_photo)
async def save_start_image_from_upload(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return

    url = first_image_url_from_message_body(event.message.body)
    if not url:
        await event.message.answer(
            "Не удалось принять вложение. Отправьте как фото или как файл-картинку (png, jpg…)."
        )
        return

    try:
        await replace_stored_start_image(url)
    except Exception as e:
        await event.message.answer(f"Не удалось сохранить: {e}")
        return

    await context.set_state(EditStartImage.menu)
    text = await _start_image_menu_text()
    await event.message.answer("Картинка сохранена.")
    await event.message.answer(
        text=text,
        attachments=[_start_image_menu_keyboard().as_markup()],
    )


@router.message_callback(EditPromoFollowup.menu, F.callback.payload == "promo_fw_back")
async def promo_followup_back_to_replics(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditReplic.choosing_replic)
    if event.message:
        await event.message.edit(
            text="Выберите реплику для редактирования:",
            attachments=[_edit_replics_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditPromoFollowup.menu, F.callback.payload == "promo_fw_text")
async def promo_followup_begin_text(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditPromoFollowup.editing_text)
    current = await get_replic("promo_followup_message")
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload="promo_fw_cancel"))
    if current.strip():
        head = f"Текущий текст:\n{current}\n\nОтправьте новый текст:"
    else:
        head = "Текст не задан (к картинке будет только невидимая подпись).\n\nОтправьте новый текст:"
    if event.message:
        await event.message.edit(text=head, attachments=[kb.as_markup()])
    await _ack_callback(event)


@router.message_callback(
    EditPromoFollowup.editing_text, F.callback.payload == "promo_fw_cancel"
)
async def promo_followup_cancel_text(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditPromoFollowup.menu)
    text = await _promo_followup_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_promo_followup_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_created(EditPromoFollowup.editing_text)
async def save_promo_followup_text(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    if not event.message.body or not event.message.body.text:
        return

    new_text = event.message.body.text

    def _save(data):
        data.setdefault("replics", {})["promo_followup_message"] = new_text

    await mutate_store(_save)

    await context.set_state(EditPromoFollowup.menu)
    text = await _promo_followup_menu_text()
    await event.message.answer("Текст сохранён.")
    await event.message.answer(
        text=text,
        attachments=[_promo_followup_menu_keyboard().as_markup()],
    )


@router.message_callback(EditPromoFollowup.menu, F.callback.payload == "promo_fw_upload")
async def promo_followup_begin_upload(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditPromoFollowup.waiting_photo)
    if event.message:
        await event.message.edit(
            text="Отправьте изображение (фото).",
            attachments=[_promo_followup_wait_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditPromoFollowup.menu, F.callback.payload == "promo_fw_delete")
async def promo_followup_delete_stored(event: MessageCallback, context: MemoryContext):
    await delete_stored_promo_followup_image()
    text = await _promo_followup_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_promo_followup_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditPromoFollowup.menu, F.callback.payload == "promo_fw_link")
async def promo_followup_begin_link(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditPromoFollowup.editing_link)
    data = await read_store()
    current = (data.get("promo_followup_button_url") or "").strip()
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload="promo_fw_cancel"))
    if current:
        head = f"Текущая ссылка:\n{current}\n\nОтправьте новый URL (https://...):"
    else:
        head = "Ссылка не задана.\n\nОтправьте URL (https://...):"
    if event.message:
        await event.message.edit(text=head, attachments=[kb.as_markup()])
    await _ack_callback(event)


@router.message_callback(EditPromoFollowup.menu, F.callback.payload == "promo_fw_link_delete")
async def promo_followup_delete_link(event: MessageCallback, context: MemoryContext):
    await clear_promo_followup_button_url()
    text = await _promo_followup_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_promo_followup_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(
    EditPromoFollowup.editing_link, F.callback.payload == "promo_fw_cancel"
)
async def promo_followup_cancel_link(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditPromoFollowup.menu)
    text = await _promo_followup_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_promo_followup_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_created(EditPromoFollowup.editing_link)
async def save_promo_followup_link(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    if not event.message.body or not event.message.body.text:
        return

    raw = event.message.body.text.strip()
    normalized = normalize_promo_followup_button_url(raw)
    if not normalized:
        await event.message.answer(
            "Нужен корректный URL, начинающийся с https:// или http://"
        )
        return

    def _save(data):
        data["promo_followup_button_url"] = normalized

    await mutate_store(_save)

    await context.set_state(EditPromoFollowup.menu)
    text = await _promo_followup_menu_text()
    await event.message.answer("Ссылка сохранена.")
    await event.message.answer(
        text=text,
        attachments=[_promo_followup_menu_keyboard().as_markup()],
    )


@router.message_callback(EditPromoFollowup.menu, F.callback.payload == "promo_fw_btn_label")
async def promo_followup_begin_button_label(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditPromoFollowup.editing_button_label)
    current = await get_replic("promo_followup_link_button_text")
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload="promo_fw_cancel"))
    head = f"Текст на кнопке-ссылке под акцией.\n\nСейчас: {current}\n\nОтправьте новый текст:"
    if event.message:
        await event.message.edit(text=head, attachments=[kb.as_markup()])
    await _ack_callback(event)


@router.message_callback(
    EditPromoFollowup.editing_button_label, F.callback.payload == "promo_fw_cancel"
)
async def promo_followup_cancel_button_label(
    event: MessageCallback, context: MemoryContext
):
    await context.set_state(EditPromoFollowup.menu)
    text = await _promo_followup_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_promo_followup_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_created(EditPromoFollowup.editing_button_label)
async def save_promo_followup_button_label(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    if not event.message.body or not event.message.body.text:
        return

    new_text = event.message.body.text.strip()
    if not new_text:
        await event.message.answer("Текст не может быть пустым.")
        return

    def _save(data):
        data.setdefault("replics", {})["promo_followup_link_button_text"] = new_text

    await mutate_store(_save)

    await context.set_state(EditPromoFollowup.menu)
    text = await _promo_followup_menu_text()
    await event.message.answer("Текст кнопки сохранён.")
    await event.message.answer(
        text=text,
        attachments=[_promo_followup_menu_keyboard().as_markup()],
    )


@router.message_callback(
    EditPromoFollowup.waiting_photo, F.callback.payload == "promo_fw_cancel"
)
async def promo_followup_cancel_upload(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditPromoFollowup.menu)
    text = await _promo_followup_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_promo_followup_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(
    EditPromoFollowup.waiting_photo, F.callback.payload == "promo_fw_nop"
)
async def promo_followup_wait_nop(event: MessageCallback, context: MemoryContext):
    await _ack_callback(event, notification=" ")


@router.message_created(EditPromoFollowup.waiting_photo)
async def save_promo_followup_from_upload(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return

    url = first_image_url_from_message_body(event.message.body)
    if not url:
        await event.message.answer(
            "Не удалось принять вложение. Отправьте как фото или как файл-картинку (png, jpg…)."
        )
        return

    try:
        await replace_stored_promo_followup_image(url)
    except Exception as e:
        await event.message.answer(f"Не удалось сохранить: {e}")
        return

    await context.set_state(EditPromoFollowup.menu)
    text = await _promo_followup_menu_text()
    await event.message.answer("Картинка сохранена.")
    await event.message.answer(
        text=text,
        attachments=[_promo_followup_menu_keyboard().as_markup()],
    )


@router.message_callback(EditBotStartedDesc.menu, F.callback.payload == "bsd_back")
async def bot_started_desc_back_to_replics(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditReplic.choosing_replic)
    if event.message:
        await event.message.edit(
            text="Выберите реплику для редактирования:",
            attachments=[_edit_replics_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditBotStartedDesc.menu, F.callback.payload == "bsd_text")
async def bot_started_desc_begin_text(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditBotStartedDesc.editing_text)
    current = await get_replic("bot_started_description")
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload="bsd_cancel"))
    if current.strip():
        head = f"Текущий текст:\n{current}\n\nОтправьте новый текст:"
    else:
        head = "Текст не задан.\n\nОтправьте новый текст:"
    if event.message:
        await event.message.edit(text=head, attachments=[kb.as_markup()])
    await _ack_callback(event)


@router.message_callback(
    EditBotStartedDesc.editing_text, F.callback.payload == "bsd_cancel"
)
async def bot_started_desc_cancel_text(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditBotStartedDesc.menu)
    text = await _bot_started_desc_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_bot_started_desc_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_created(EditBotStartedDesc.editing_text)
async def save_bot_started_desc_text(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    if not event.message.body or not event.message.body.text:
        return

    new_text = event.message.body.text

    def _save(data):
        data.setdefault("replics", {})["bot_started_description"] = new_text

    await mutate_store(_save)

    await context.set_state(EditBotStartedDesc.menu)
    text = await _bot_started_desc_menu_text()
    await event.message.answer("Текст сохранён.")
    await event.message.answer(
        text=text,
        attachments=[_bot_started_desc_menu_keyboard().as_markup()],
    )


@router.message_callback(EditBotStartedDesc.menu, F.callback.payload == "bsd_upload")
async def bot_started_desc_begin_upload(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditBotStartedDesc.waiting_photo)
    if event.message:
        await event.message.edit(
            text="Отправьте изображение (фото).",
            attachments=[_bot_started_desc_wait_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(EditBotStartedDesc.menu, F.callback.payload == "bsd_delete")
async def bot_started_desc_delete_stored(event: MessageCallback, context: MemoryContext):
    await delete_stored_bot_started_description_image()
    text = await _bot_started_desc_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_bot_started_desc_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(
    EditBotStartedDesc.waiting_photo, F.callback.payload == "bsd_cancel"
)
async def bot_started_desc_cancel_upload(event: MessageCallback, context: MemoryContext):
    await context.set_state(EditBotStartedDesc.menu)
    text = await _bot_started_desc_menu_text()
    if event.message:
        await event.message.edit(
            text=text,
            attachments=[_bot_started_desc_menu_keyboard().as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(
    EditBotStartedDesc.waiting_photo, F.callback.payload == "bsd_nop"
)
async def bot_started_desc_wait_nop(event: MessageCallback, context: MemoryContext):
    await _ack_callback(event, notification=" ")


@router.message_created(EditBotStartedDesc.waiting_photo)
async def save_bot_started_desc_from_upload(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return

    url = first_image_url_from_message_body(event.message.body)
    if not url:
        await event.message.answer(
            "Не удалось принять вложение. Отправьте как фото или как файл-картинку (png, jpg…)."
        )
        return

    try:
        await replace_stored_bot_started_description_image(url)
    except Exception as e:
        await event.message.answer(f"Не удалось сохранить: {e}")
        return

    await context.set_state(EditBotStartedDesc.menu)
    text = await _bot_started_desc_menu_text()
    await event.message.answer("Картинка сохранена.")
    await event.message.answer(
        text=text,
        attachments=[_bot_started_desc_menu_keyboard().as_markup()],
    )


async def manage_channels_message(message, *, edit: bool = False):
    """message — maxapi.types.message.Message с .answer / .edit."""
    channels = await get_all_channels()
    kb = InlineKeyboardBuilder()

    for channel in channels:
        status = "✅" if channel["is_active"] else "❌"
        display_name = channel["name"] or channel["username"]
        kb.row(
            CallbackButton(
                text=f"{status} {display_name}",
                payload=f"channel_{channel['id']}",
            )
        )

    kb.row(CallbackButton(text="➕ Добавить канал", payload="add_channel"))
    kb.row(CallbackButton(text="⬅️ Назад", payload="cancel_channels"))

    text = "Управление каналами:"
    att = kb.as_markup()
    if edit and message.body:
        await message.edit(text=text, attachments=[att])
    else:
        await message.answer(text=text, attachments=[att])


@router.message_created(Command("channels"))
async def manage_channels_cmd(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    await context.clear()
    await manage_channels_message(event.message)


@router.message_callback(F.callback.payload.startswith("toggle_"))
async def channel_toggle_handler(event: MessageCallback):
    raw = _after_prefix("toggle_", event.callback.payload or "")
    try:
        channel_id = int(raw)
    except ValueError:
        await _ack_callback(event)
        return

    success = await toggle_channel(channel_id)
    if success and event.message:
        channel = await get_channel(channel_id)
        if channel:
            status_btn_text = (
                "❌ Деактивировать" if channel["is_active"] else "✅ Активировать"
            )
            kb = InlineKeyboardBuilder()
            kb.row(
                CallbackButton(
                    text=status_btn_text, payload=f"toggle_{channel_id}"
                )
            )
            kb.row(
                CallbackButton(
                    text="✏️ Изменить название",
                    payload=f"edit_name_{channel_id}",
                )
            )
            kb.row(
                CallbackButton(
                    text="🔗 Изменить ссылку",
                    payload=f"edit_link_{channel_id}",
                )
            )
            kb.row(
                CallbackButton(
                    text="🗑️ Удалить канал", payload=f"delete_{channel_id}"
                )
            )
            kb.row(CallbackButton(text="⬅️ Назад", payload="cancel_channels"))

            await event.message.edit(
                text=(
                    f"Управление каналом:\n\n"
                    f"ID: {channel['id']}\n"
                    f"Username: {channel['username']}\n"
                    f"Название: {channel['name'] or 'Не задано'}\n"
                    f"Ссылка: {channel['link'] or 'Не задана'}\n"
                    f"Статус: {'Активен' if channel['is_active'] else 'Неактивен'}"
                ),
                attachments=[kb.as_markup()],
            )
    await _ack_callback(event)


@router.message_callback(F.callback.payload.startswith("edit_name_"))
async def channel_edit_name_handler(event: MessageCallback, context: MemoryContext):
    raw = _after_prefix("edit_name_", event.callback.payload or "")
    try:
        channel_id = int(raw)
    except ValueError:
        await _ack_callback(event)
        return

    await context.update_data(channel_id=channel_id)
    await context.set_state(ChannelManage.editing_name)

    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload=f"channel_{channel_id}"))

    if event.message:
        await event.message.edit(
            text="Введите новое название канала:",
            attachments=[kb.as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(F.callback.payload.startswith("edit_link_"))
async def channel_edit_link_handler(event: MessageCallback, context: MemoryContext):
    raw = _after_prefix("edit_link_", event.callback.payload or "")
    try:
        channel_id = int(raw)
    except ValueError:
        await _ack_callback(event)
        return

    await context.update_data(channel_id=channel_id)
    await context.set_state(ChannelManage.editing_link)

    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload=f"channel_{channel_id}"))

    if event.message:
        await event.message.edit(
            text=(
                "Введите новую ссылку канала "
                "(должна начинаться с https:// или http://):"
            ),
            attachments=[kb.as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(F.callback.payload.startswith("delete_"))
async def channel_delete_handler(event: MessageCallback, context: MemoryContext):
    payload = event.callback.payload or ""
    raw = _after_prefix("delete_", payload)
    try:
        channel_id = int(raw)
    except ValueError:
        await _ack_callback(event)
        return

    await context.update_data(channel_id=channel_id)
    await context.set_state(ChannelManage.confirming_delete)

    channel = await get_channel(channel_id)
    if not channel or not event.message:
        await _ack_callback(event)
        return

    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(
            text="✅ Да", payload=f"confirm_delete_{channel_id}"
        ),
        CallbackButton(
            text="❌ Нет", payload=f"channel_{channel_id}"
        ),
    )

    await event.message.edit(
        text=(
            f"Вы уверены, что хотите удалить канал "
            f"{channel['name'] or channel['username']}?"
        ),
        attachments=[kb.as_markup()],
    )
    await _ack_callback(event)


@router.message_callback(F.callback.payload.startswith("confirm_delete_"))
async def channel_confirm_delete_handler(event: MessageCallback, context: MemoryContext):
    raw = _after_prefix("confirm_delete_", event.callback.payload or "")
    try:
        channel_id = int(raw)
    except ValueError:
        await _ack_callback(event)
        return

    success = await delete_channel(channel_id)
    if success and event.message:
        await event.message.edit(text="Канал успешно удален!", attachments=[])
        await manage_channels_message(event.message)

    await context.clear()
    await _ack_callback(event)


@router.message_callback(F.callback.payload == "cancel_channels")
async def cancel_channels_handler(event: MessageCallback, context: MemoryContext):
    await context.clear()
    if event.message:
        await event.message.edit(text="Управление каналами завершено.", attachments=[])
        await event.message.answer(INFO_TEXT)
    await _ack_callback(event)


@router.message_callback(F.callback.payload.startswith("channel_"))
async def channel_action_handler(event: MessageCallback, context: MemoryContext):
    payload = event.callback.payload or ""
    raw = _after_prefix("channel_", payload)
    try:
        channel_id = int(raw)
    except ValueError:
        await _ack_callback(event)
        return

    if await context.get_state() == ChannelManage.adding_channel:
        await context.clear()

    channel = await get_channel(channel_id)
    if not channel or not event.message:
        await _ack_callback(event, notification="Канал не найден")
        return

    await context.update_data(channel_id=channel_id)

    status_btn_text = (
        "❌ Деактивировать" if channel["is_active"] else "✅ Активировать"
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text=status_btn_text, payload=f"toggle_{channel_id}")
    )
    kb.row(
        CallbackButton(
            text="✏️ Изменить название", payload=f"edit_name_{channel_id}"
        )
    )
    kb.row(
        CallbackButton(
            text="🔗 Изменить ссылку", payload=f"edit_link_{channel_id}"
        )
    )
    kb.row(
        CallbackButton(text="🗑️ Удалить канал", payload=f"delete_{channel_id}")
    )
    kb.row(CallbackButton(text="⬅️ Назад", payload="cancel_channels"))

    await event.message.edit(
        text=(
            f"Управление каналом:\n\n"
            f"ID: {channel['id']}\n"
            f"Username: {channel['username']}\n"
            f"Название: {channel['name'] or 'Не задано'}\n"
            f"Ссылка: {channel['link'] or 'Не задана'}\n"
            f"Статус: {'Активен' if channel['is_active'] else 'Неактивен'}"
        ),
        attachments=[kb.as_markup()],
    )
    await _ack_callback(event)


@router.message_created(ChannelManage.editing_name)
async def process_edit_name(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    if not event.message.body or not event.message.body.text:
        return

    data = await context.get_data()
    channel_id = data.get("channel_id")
    new_name = event.message.body.text

    success = await update_channel(channel_id, name=new_name)
    if success:
        await event.message.answer("Название канала успешно обновлено!")
    else:
        await event.message.answer("Ошибка при обновлении названия канала.")

    await context.clear()
    await manage_channels_message(event.message)


@router.message_created(ChannelManage.editing_link)
async def process_edit_link(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    if not event.message.body or not event.message.body.text:
        return

    data = await context.get_data()
    channel_id = data.get("channel_id")
    new_link = event.message.body.text

    try:
        success = await update_channel(channel_id, link=new_link)
        if success:
            await event.message.answer("Ссылка канала успешно обновлена!")
        else:
            await event.message.answer("Ошибка при обновлении ссылки канала.")
    except ValueError as e:
        await event.message.answer(str(e))

    await context.clear()
    await manage_channels_message(event.message)


@router.message_created(Command("stats"))
async def cmd_stats(event: MessageCreated):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return

    count = await get_counter()
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="🔄 Обнулить счетчик", payload="reset_counter"))

    await event.message.answer(
        f"Всего выдано промокодов: {count}",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload == "reset_counter")
async def reset_counter_handler(event: MessageCallback):
    if event.callback.user.user_id not in settings.ADMINS:
        await _ack_callback(event)
        return

    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="✅ Да", payload="confirm_reset"),
        CallbackButton(text="❌ Нет", payload="cancel_reset"),
    )

    if event.message:
        await event.message.edit(
            text="Вы уверены, что хотите обнулить счетчик?",
            attachments=[kb.as_markup()],
        )
    await _ack_callback(event)


@router.message_callback(F.callback.payload == "confirm_reset")
async def confirm_reset_handler(event: MessageCallback):
    if event.callback.user.user_id not in settings.ADMINS:
        await _ack_callback(event)
        return

    await reset_counter()
    if event.message:
        await event.message.edit(text="Счетчик обнулен!", attachments=[])
    await _ack_callback(event)


@router.message_callback(F.callback.payload == "cancel_reset")
async def cancel_reset_handler(event: MessageCallback):
    if event.message:
        await event.message.edit(text="Отмена обнуления счетчика", attachments=[])
    await _ack_callback(event)


@router.message_callback(F.callback.payload == "add_channel")
async def add_channel_handler(event: MessageCallback, context: MemoryContext):
    await context.set_state(ChannelManage.adding_channel)

    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload="cancel_channels"))

    if event.message:
        await event.message.edit(
            text=(
                "Одной строкой:\n"
                "• числовой chat_id канала (как в MAX; допустим знак «-»)\n"
                "• или ссылку без @ в пути: https://max.ru/channelname\n"
                "• или короче: @channelname или channelname"
            ),
            attachments=[kb.as_markup()],
        )
    await _ack_callback(event)


@router.message_created(ChannelManage.adding_channel)
async def process_add_channel(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    if not event.message.body or not event.message.body.text:
        return

    text = event.message.body.text
    try:
        bot = event._ensure_bot()
        channel_id, username, name, link = await parse_admin_channel_input(
            bot, text
        )
        success = await add_channel(channel_id, username, name, link)

        if success:
            await event.message.answer("Канал успешно добавлен!")
        else:
            await event.message.answer("Ошибка: канал с таким ID уже существует.")

    except ValueError as e:
        await event.message.answer(str(e) or "Ошибка ввода.")
        return
    except Exception as e:
        await event.message.answer(f"Ошибка при добавлении канала: {e!s}")
        return

    await context.clear()
    await manage_channels_message(event.message)
