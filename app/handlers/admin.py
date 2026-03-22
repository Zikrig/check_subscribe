# app/handlers/admin — MAX Bot API

from maxapi import F, Router
from maxapi.context.context import MemoryContext
from maxapi.context.state_machine import State, StatesGroup
from maxapi.filters.command import Command
from maxapi.types import CallbackButton, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.config import settings
from app.services.channels import (
    add_channel,
    delete_channel,
    get_all_channels,
    get_channel,
    resolve_max_chat_id,
    toggle_channel,
    update_channel,
)
from app.services.counters import get_counter, reset_counter
from app.services.replics import get_replic
from app.services.storage import mutate_store
from app.services.sheets import update_table

router = Router("admin")

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


@router.message_created(Command("edit_replics"))
async def cmd_edit_replics(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return

    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="Стартовое сообщение", payload="edit_start"),
        CallbackButton(text="Сообщение об успехе", payload="edit_success"),
    )
    kb.row(
        CallbackButton(text="Сообщение о неподписке", payload="edit_not_subbed"),
    )
    kb.row(CallbackButton(text="Назад", payload="cancel_edit"))

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
    await event.answer()


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
        await event.answer()
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
    await event.answer()


@router.message_callback(EditReplic.editing_text, F.callback.payload == "cancel_edit")
async def cancel_edit_replic(event: MessageCallback, context: MemoryContext):
    await context.clear()
    if event.message:
        await event.message.edit(text="Редактирование отменено.", attachments=[])
        await event.message.answer(INFO_TEXT)
    await event.answer()


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


async def manage_channels_message(message, *, edit: bool = False):
    """message — maxapi.types.message.Message с .answer / .edit."""
    channels = await get_all_channels()
    kb = InlineKeyboardBuilder()

    for channel in channels:
        status = "✅" if channel.is_active else "❌"
        display_name = channel.name or channel.username
        kb.row(
            CallbackButton(
                text=f"{status} {display_name}",
                payload=f"channel_{channel.id}",
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
        await event.answer()
        return

    success = await toggle_channel(channel_id)
    if success and event.message:
        channel = await get_channel(channel_id)
        if channel:
            status_btn_text = (
                "❌ Деактивировать" if channel.is_active else "✅ Активировать"
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
                    f"ID: {channel.id}\n"
                    f"Username: {channel.username}\n"
                    f"Название: {channel.name or 'Не задано'}\n"
                    f"Ссылка: {channel.link or 'Не задана'}\n"
                    f"Статус: {'Активен' if channel.is_active else 'Неактивен'}"
                ),
                attachments=[kb.as_markup()],
            )
    await event.answer()


@router.message_callback(F.callback.payload.startswith("edit_name_"))
async def channel_edit_name_handler(event: MessageCallback, context: MemoryContext):
    raw = _after_prefix("edit_name_", event.callback.payload or "")
    try:
        channel_id = int(raw)
    except ValueError:
        await event.answer()
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
    await event.answer()


@router.message_callback(F.callback.payload.startswith("edit_link_"))
async def channel_edit_link_handler(event: MessageCallback, context: MemoryContext):
    raw = _after_prefix("edit_link_", event.callback.payload or "")
    try:
        channel_id = int(raw)
    except ValueError:
        await event.answer()
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
    await event.answer()


@router.message_callback(F.callback.payload.startswith("delete_"))
async def channel_delete_handler(event: MessageCallback, context: MemoryContext):
    payload = event.callback.payload or ""
    raw = _after_prefix("delete_", payload)
    try:
        channel_id = int(raw)
    except ValueError:
        await event.answer()
        return

    await context.update_data(channel_id=channel_id)
    await context.set_state(ChannelManage.confirming_delete)

    channel = await get_channel(channel_id)
    if not channel or not event.message:
        await event.answer()
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
            f"{channel.name or channel.username}?"
        ),
        attachments=[kb.as_markup()],
    )
    await event.answer()


@router.message_callback(F.callback.payload.startswith("confirm_delete_"))
async def channel_confirm_delete_handler(event: MessageCallback, context: MemoryContext):
    raw = _after_prefix("confirm_delete_", event.callback.payload or "")
    try:
        channel_id = int(raw)
    except ValueError:
        await event.answer()
        return

    success = await delete_channel(channel_id)
    if success and event.message:
        await event.message.edit(text="Канал успешно удален!", attachments=[])
        await manage_channels_message(event.message)

    await context.clear()
    await event.answer()


@router.message_callback(F.callback.payload == "cancel_channels")
async def cancel_channels_handler(event: MessageCallback, context: MemoryContext):
    await context.clear()
    if event.message:
        await event.message.edit(text="Управление каналами завершено.", attachments=[])
        await event.message.answer(INFO_TEXT)
    await event.answer()


@router.message_callback(F.callback.payload.startswith("channel_"))
async def channel_action_handler(event: MessageCallback, context: MemoryContext):
    payload = event.callback.payload or ""
    raw = _after_prefix("channel_", payload)
    try:
        channel_id = int(raw)
    except ValueError:
        await event.answer()
        return

    if await context.get_state() == ChannelManage.adding_channel:
        await context.clear()

    channel = await get_channel(channel_id)
    if not channel or not event.message:
        await event.answer(notification="Канал не найден")
        return

    await context.update_data(channel_id=channel_id)

    status_btn_text = (
        "❌ Деактивировать" if channel.is_active else "✅ Активировать"
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
            f"ID: {channel.id}\n"
            f"Username: {channel.username}\n"
            f"Название: {channel.name or 'Не задано'}\n"
            f"Ссылка: {channel.link or 'Не задана'}\n"
            f"Статус: {'Активен' if channel.is_active else 'Неактивен'}"
        ),
        attachments=[kb.as_markup()],
    )
    await event.answer()


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
        await event.answer()
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
    await event.answer()


@router.message_callback(F.callback.payload == "confirm_reset")
async def confirm_reset_handler(event: MessageCallback):
    if event.callback.user.user_id not in settings.ADMINS:
        await event.answer()
        return

    await reset_counter()
    if event.message:
        await event.message.edit(text="Счетчик обнулен!", attachments=[])
    await event.answer()


@router.message_callback(F.callback.payload == "cancel_reset")
async def cancel_reset_handler(event: MessageCallback):
    if event.message:
        await event.message.edit(text="Отмена обнуления счетчика", attachments=[])
    await event.answer()


@router.message_callback(F.callback.payload == "add_channel")
async def add_channel_handler(event: MessageCallback, context: MemoryContext):
    await context.set_state(ChannelManage.adding_channel)

    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отменить", payload="cancel_channels"))

    if event.message:
        await event.message.edit(
            text=(
                "Введите данные канала в формате:\n"
                "id username [name] [link]\n\n"
                "id — chat_id из MAX (часто с минусом в начале, см. list_max_chats.py).\n\n"
                "Пример:\n"
                "-10012345678 channel_username Название канала "
                "https://example.com/channel"
            ),
            attachments=[kb.as_markup()],
        )
    await event.answer()


@router.message_created(ChannelManage.adding_channel)
async def process_add_channel(event: MessageCreated, context: MemoryContext):
    if not event.message.sender or event.message.sender.user_id not in settings.ADMINS:
        return
    if not event.message.body or not event.message.body.text:
        return

    text = event.message.body.text
    try:
        parts = text.split()
        if len(parts) < 2:
            await event.message.answer(
                "Ошибка: недостаточно данных. Нужно как минимум id и username."
            )
            return

        bot = event._ensure_bot()
        channel_id = await resolve_max_chat_id(bot, int(parts[0]))
        username = parts[1]
        name = " ".join(parts[2:]) if len(parts) > 2 else None
        link = None

        for part in parts[2:]:
            if part.startswith(("http://", "https://", "max.ru/")):
                link = part
                if name:
                    name = name.replace(part, "").strip()
                break

        success = await add_channel(channel_id, username, name, link)

        if success:
            await event.message.answer("Канал успешно добавлен!")
        else:
            await event.message.answer("Ошибка: канал с таким ID уже существует.")

    except ValueError:
        await event.message.answer("Ошибка: ID канала должен быть числом.")
        return
    except Exception as e:
        await event.message.answer(f"Ошибка при добавлении канала: {e!s}")
        return

    await context.clear()
    await manage_channels_message(event.message)
