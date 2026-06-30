from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


shift_type_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="☀️ Дневная"),
            KeyboardButton(text="🌙 Ночная"),
        ],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="❌ Отмена"),
        ],
    ],
    resize_keyboard=True,
)
