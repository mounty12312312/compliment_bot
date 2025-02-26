from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
import random
import os
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

class Form(StatesGroup):
    user_gender = State()
    target_gender = State()
    compliment_text = State()
    edit_compliment = State()
    moderate_page = State()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

ADMIN_IDS = [348020551, 676359311]  # Список разрешенных ID

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id  # Получаем telegram_id пользователя
    print(f"User ID: {user_id}")
    
    # Проверяем, существует ли уже комплимент от этого пользователя
    async with aiosqlite.connect('compliments.db') as db:
        async with db.execute("SELECT COUNT(*) FROM compliments WHERE id = ?", (user_id,)) as cursor:
            count = await cursor.fetchone()
            if count[0] > 0:
                await message.answer("Вы уже отправили комплимент. Пожалуйста, подождите до следующего раза.")
                return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской", callback_data="gender_male")],
        [InlineKeyboardButton(text="Женский", callback_data="gender_female")]
    ])
    await message.answer("Выберите ваш пол:", reply_markup=keyboard)
    await state.set_state(Form.user_gender)

# Обработчик inline-кнопок
@dp.callback_query(Form.user_gender, F.data.startswith("gender_"))
async def process_user_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = "Мужской" if callback.data == "gender_male" else "Женский"
    await state.update_data(user_gender=gender)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской", callback_data="target_male")],
        [InlineKeyboardButton(text="Женский", callback_data="target_female")]
    ])
    await callback.message.edit_text("Для кого будет комплимент?", reply_markup=keyboard)
    await state.set_state(Form.target_gender)

@dp.callback_query(Form.target_gender, F.data.startswith("target_"))
async def process_target_gender(callback: types.CallbackQuery, state: FSMContext):
    target_gender = "Мужской" if callback.data == "target_male" else "Женский"
    await state.update_data(target_gender=target_gender)
    await callback.message.edit_text("Напишите комплимент:")
    await state.set_state(Form.compliment_text)

# Инициализация БД с начальными значениями
async def init_db():
    async with aiosqlite.connect('compliments.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS compliments (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                target_gender TEXT NOT NULL,
                is_approved BOOLEAN DEFAULT 0
            )
        ''')
        await db.commit()
        
        # Проверяем, есть ли уже записи в таблице
        async with db.execute("SELECT COUNT(*) FROM compliments") as cursor:
            count = await cursor.fetchone()
            if count[0] == 0:
                # Добавляем начальные значения
                compliments_male = [
                    ("1", "Вы сильные!", "Мужской", 1),
                    ("2", "Пусть работа будет мёдом!", "Мужской", 1),
                    ("3", "Самые умные мужчинки на свете!", "Мужской", 1),
                    ("4", "Ваше мужское на высоте!", "Мужской", 1),
                    ("5", "Наши спасители!", "Мужской", 1)
                ]
                
                compliments_female = [
                    ("6", "Самые красивые из красивых!", "Женский", 1),
                    ("7", "Красоточки, всем привет!", "Женский", 1),
                    ("8", "Лучшие на свете!", "Женский", 1),
                    ("9", "Кустик роз вам всем!", "Женский", 1),
                    ("10", "Обаятельные принцессы!", "Женский", 1)
                ]
                
                all_compliments = compliments_male + compliments_female
                
                await db.executemany("INSERT INTO compliments (id, text, target_gender, is_approved) VALUES (?, ?, ?, ?)", all_compliments)
                await db.commit()

# Кнопка "Редактировать комплимент" после отправки
async def send_final_message(message: types.Message, compliment_text: str, user_data: dict):
    # Получаем случайный одобренный комплимент
    user_gender = user_data.get('user_gender')
    approved_compliment = await get_random_approved_compliment(user_gender)
    
    final_text = f"✅ Комплимент сохранен!\n\nВаш комплимент:\n{compliment_text}"
    if approved_compliment:
        final_text += f"\n\nСлучайный комплимент для вас:\n{approved_compliment}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать комплимент", callback_data="edit_last")]
    ])
    await message.answer(final_text, reply_markup=keyboard)

# Обработчик редактирования последнего комплимента
@dp.callback_query(F.data == "edit_last")
async def edit_last_compliment(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id  # Получаем telegram_id пользователя
    async with aiosqlite.connect('compliments.db') as db:
        async with db.execute("SELECT id, text, target_gender FROM compliments WHERE id = ? ORDER BY id DESC LIMIT 1", 
                            (user_id,)) as cursor:
            compliment = await cursor.fetchone()
    
    if compliment:
        # Сохраняем user_gender как target_gender, так как комплимент предназначен для этого же пола
        await state.update_data(edit_id=compliment[0], target_gender=compliment[2], user_gender=compliment[2])
        await callback.message.edit_text(f"Текущий текст: {compliment[1]}\nВведите новый текст:")
        await state.set_state(Form.compliment_text)
        await callback.answer()
    else:
        await callback.answer("❌ Не найдено комплиментов для редактирования")

# Обработчик сохранения нового текста комплимента
@dp.message(Form.compliment_text)
async def save_new_compliment_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await state.get_data()
    edit_id = user_data.get('edit_id')
    
    if edit_id:
        async with aiosqlite.connect('compliments.db') as db:
            await db.execute("UPDATE compliments SET text = ? WHERE id = ?", (message.text, edit_id))
            await db.commit()
        
        await send_final_message(message, message.text, user_data)
        await state.clear()
    else:
        target_gender = user_data.get('target_gender')
        if not target_gender:
            await message.answer("Пожалуйста, укажите целевую аудиторию для комплимента.")
            return
        
        async with aiosqlite.connect('compliments.db') as db:
            await db.execute("INSERT INTO compliments (id, text, target_gender) VALUES (?, ?, ?)",
                            (str(user_id), message.text, target_gender))
            await db.commit()
        
        await send_final_message(message, message.text, user_data)
        await state.clear()

# Модерация с лимитом 10 комплиментов
@dp.message(Command("moderate"))
async def cmd_moderate(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде")
        return
    
    await state.update_data(page=0)
    await show_moderation_page(message, state)

async def show_moderation_page(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    
    async with aiosqlite.connect('compliments.db') as db:
        async with db.execute("SELECT id, text FROM compliments WHERE is_approved = 0 LIMIT 10") as cursor:
            compliments = await cursor.fetchall()
    
    if not compliments:
        moderation_message_id = user_data.get('moderation_message_id')
        if moderation_message_id:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=moderation_message_id,
                text="✅ Все комплименты проверены!"
            )
        else:
            await message.answer("✅ Все комплименты проверены!")
        return
    
    text = "Список на модерацию:\n\n" + "\n".join(
        [f"{idx+1}. {compliment[1]}" for idx, compliment in enumerate(compliments)]
    )
    
    # Сохраняем текущие комплименты в состоянии
    await state.update_data(current_compliments=compliments)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Одобрить {idx+1}", callback_data=f"approve_{compliment[0]}"),
         InlineKeyboardButton(text=f"❌ Удалить {idx+1}", callback_data=f"delete_{compliment[0]}")]
        for idx, compliment in enumerate(compliments)
    ] + [[
        InlineKeyboardButton(text=" Одобрить все", callback_data="approve_all"),
        InlineKeyboardButton(text="Отклонить все", callback_data="delete_all")
    ]])
    
    # Сохраняем сообщение для последующего редактирования
    moderation_message_id = user_data.get('moderation_message_id')
    if moderation_message_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=moderation_message_id,
                text=text,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Ошибка при редактировании сообщения: {e}")
            # Если сообщение нельзя отредактировать, отправляем новое
            new_message = await message.answer(text, reply_markup=keyboard)
            await state.update_data(moderation_message_id=new_message.message_id)
    else:
        new_message = await message.answer(text, reply_markup=keyboard)
        await state.update_data(moderation_message_id=new_message.message_id)

# Обработчик одобрения/удаления комплимента
@dp.callback_query(F.data.startswith("approve_") | F.data.startswith("delete_"))
async def process_moderation(callback: types.CallbackQuery, state: FSMContext):
    action, compliment_id = callback.data.split("_")
    user_data = await state.get_data()  # Получаем данные состояния
    current_compliments = user_data.get('current_compliments', [])
    
    async with aiosqlite.connect('compliments.db') as db:
        if action == "approve" and compliment_id != "all":
            await db.execute("UPDATE compliments SET is_approved = 1 WHERE id = ?", (compliment_id,))
        elif action == "delete" and compliment_id != "all":
            await db.execute("DELETE FROM compliments WHERE id = ?", (compliment_id,))
        elif compliment_id == "all":
            compliment_ids = [comp[0] for comp in current_compliments]
            if action == "approve":
                await db.executemany("UPDATE compliments SET is_approved = 1 WHERE id = ?", 
                                   [(id,) for id in compliment_ids])
            elif action == "delete":
                await db.executemany("DELETE FROM compliments WHERE id = ?", 
                                   [(id,) for id in compliment_ids])
        
        await db.commit()
    
    # Обновляем текущие комплименты в состоянии
    await state.update_data(current_compliments=[])
    
    await show_moderation_page(callback.message, state)
    await callback.answer()

# Функция для получения случайного одобренного комплимента
async def get_random_approved_compliment(target_gender: str):
    async with aiosqlite.connect('compliments.db') as db:
        async with db.execute("SELECT text FROM compliments WHERE is_approved = 1 AND target_gender = ? ORDER BY RANDOM() LIMIT 1", (target_gender,)) as cursor:
            compliment = await cursor.fetchone()
            return compliment[0] if compliment else None

# Запуск бота
async def main():
    await init_db()  # Инициализация базы данных только один раз
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())