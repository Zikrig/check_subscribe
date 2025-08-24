# app/handlers/admin.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select


from app.config import settings
from app.services.sheets import update_table
from app.services.replics import get_replic
from app.services.db import SessionLocal, Replic
from app.services.channels import get_all_channels, toggle_channel

router = Router()

# Текст для команды /info
INFO_TEXT = (
    "/start — версия для пользователей\n"
    "/info — список команд\n"
    "/table — обновить таблицу\n"
    "/channels — управление каналами\n"
    "/edit_replics — редактировать реплики"
)
class EditReplic(StatesGroup):
    choosing_replic = State()
    editing_text = State()

@router.message(F.text == "/table")
async def cmd_table(message: Message):
    if not message.from_user.id in settings.ADMINS:
        return
    await update_table()
    await message.answer("Таблица актуализирована!")

@router.message(F.text == "/info")
async def cmd_info(message: Message):
    if not message.from_user.id in settings.ADMINS:
        return
    await message.answer(INFO_TEXT)

@router.message(F.text == "/edit_replics")
async def cmd_edit_replics(message: Message, state: FSMContext):
    if message.from_user.id not in settings.ADMINS:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Стартовое сообщение", callback_data="edit_start")],
        [InlineKeyboardButton(text="Сообщение об успехе", callback_data="edit_success")],
        [InlineKeyboardButton(text="Сообщение о неподписке", callback_data="edit_not_subbed")],
        [InlineKeyboardButton(text="Назад", callback_data="cancel_edit")]
    ])
    
    await message.answer("Выберите реплику для редактирования:", reply_markup=keyboard)
    await state.set_state(EditReplic.choosing_replic)

@router.callback_query(StateFilter(EditReplic.choosing_replic))
async def choose_replic(callback: CallbackQuery, state: FSMContext):
    if callback.data == "cancel_edit":
        await state.clear()
        await callback.message.edit_text("Редактирование отменено.")
        await callback.message.answer(INFO_TEXT)
        await callback.answer()
        return
    
    replic_map = {
        "edit_start": "start_message",
        "edit_success": "success_message", 
        "edit_not_subbed": "not_subbed_message"
    }
    
    replic_name = replic_map.get(callback.data)
    if replic_name:
        current_text = await get_replic(replic_name)
        await state.update_data(replic_name=replic_name)
        
        # Создаем клавиатуру с кнопкой отмены
        cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_edit")]
        ])
        
        await callback.message.edit_text(
            f"Текущий текст: {current_text}\n\nОтправьте новый текст:",
            reply_markup=cancel_keyboard
        )
        await state.set_state(EditReplic.editing_text)
    await callback.answer()

@router.callback_query(StateFilter(EditReplic.editing_text), F.data == "cancel_edit")
async def cancel_edit(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Редактирование отменено.")
    await callback.message.answer(INFO_TEXT)
    await callback.answer()

@router.message(StateFilter(EditReplic.editing_text))
async def save_new_replic(message: Message, state: FSMContext):
    data = await state.get_data()
    replic_name = data["replic_name"]
    new_text = message.text

    async with SessionLocal() as session:
        # Проверяем, существует ли уже запись
        result = await session.execute(
            select(Replic).where(Replic.name == replic_name)
        )
        replic = result.scalar_one_or_none()
        
        if replic:
            # Обновляем существующую запись
            replic.text = new_text
        else:
            # Создаем новую запись
            session.add(Replic(name=replic_name, text=new_text))
        
        await session.commit()

    await message.answer("Реплика успешно обновлена!")
    await state.clear()
    await message.answer(INFO_TEXT)
    
    

@router.message(F.text == "/channels")
async def manage_channels(message: Message):
    if message.from_user.id not in settings.ADMINS:
        return
    
    channels = await get_all_channels()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for channel in channels:
        status = "✅" if channel.is_active else "❌"
        button = InlineKeyboardButton(
            text=f"{status} {channel.username}",
            callback_data=f"toggle_channel_{channel.id}"
        )
        keyboard.inline_keyboard.append([button])
    
    back_button = InlineKeyboardButton(text="Назад", callback_data="cancel_channels")
    keyboard.inline_keyboard.append([back_button])
    
    await message.answer("Управление каналами:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("toggle_channel_"))
async def channel_toggle_handler(callback: CallbackQuery):
    channel_id = int(callback.data.split("_")[2])
    success = await toggle_channel(channel_id)
    
    if success:
        # Получаем обновленный список каналов
        channels = await get_all_channels()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        
        for channel in channels:
            status = "✅" if channel.is_active else "❌"
            button = InlineKeyboardButton(
                text=f"{status} {channel.username}",
                callback_data=f"toggle_channel_{channel.id}"
            )
            keyboard.inline_keyboard.append([button])
        
        back_button = InlineKeyboardButton(text="Назад", callback_data="cancel_channels")
        keyboard.inline_keyboard.append([back_button])
        
        # Обновляем текущее сообщение с новой клавиатурой
        await callback.message.edit_text("Управление каналами:", reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data == "cancel_channels")
async def cancel_channels(callback: CallbackQuery):
    await callback.message.edit_text("Управление каналами завершено.")
    await callback.message.answer(INFO_TEXT)
    await callback.answer()