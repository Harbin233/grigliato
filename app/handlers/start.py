from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from app.models.user import UserRole
from app.services.shift_service import shift_service
from app.services.user_service import user_service
from app.states.register import RegisterState

router = Router()


def keyboard(buttons: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=text) for text in row]
            for row in buttons
        ],
        resize_keyboard=True,
    )


start_keyboard = keyboard([
    ["▶ Начать регистрацию"],
])

role_keyboard = keyboard([
    ["🔧 Наладчик"],
    ["👷 Оператор"],
])

shift_keyboard = keyboard([
    ["1", "2", "3", "4"],
])

main_keyboard = keyboard([
    ["▶ Приступил к работе"],
])

shift_open_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🚀 Открыть смену",
                callback_data="open_shift",
            )
        ]
    ]
)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(
        message.from_user.id
    )

    if user:
        await state.clear()

        await message.answer(
            f"Добро пожаловать, {user.full_name}.\n\n"
            f"Смена №{user.shift_number}",
            reply_markup=main_keyboard,
        )
        return

    await state.set_state(RegisterState.full_name)

    await message.answer(
        "Добро пожаловать.\n\n"
        "Введите Ваше ФИО.",
        reply_markup=start_keyboard,
    )


@router.message(F.text == "▶ Приступил к работе")
async def start_work(
    message: Message,
):
    user = await user_service.get_by_telegram_id(
        message.from_user.id
    )

    if user is None:
        await message.answer(
            "Сначала зарегистрируйтесь."
        )
        return

    active = await shift_service.get_active_shift()

    if active is None:
        if user.role == UserRole.MECHANIC:
            await message.answer(
                "Смена еще не открыта.",
                reply_markup=shift_open_keyboard,
            )
            return

        await message.answer(
            "Смена еще не открыта.\n"
            "Дождитесь наладчика."
        )
        return

    await message.answer(
        "✅ Вы приступили к работе.\n\n"
        f"Открыта смена №{active.shift_number}."
    )


@router.callback_query(F.data == "open_shift")
async def open_shift(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )

    if user is None:
        await callback.message.answer(
            "Сначала зарегистрируйтесь."
        )
        await callback.answer()
        return

    ok, text = await shift_service.start_shift(user)

    await callback.message.answer(text)
    await callback.answer()


@router.message(F.text == "▶ Начать регистрацию")
async def start_registration(
    message: Message,
    state: FSMContext,
):
    await state.set_state(RegisterState.full_name)

    await message.answer(
        "Введите Ваше ФИО."
    )


@router.message(RegisterState.full_name)
async def input_name(
    message: Message,
    state: FSMContext,
):
    await state.update_data(
        full_name=message.text.strip()
    )

    await state.set_state(
        RegisterState.role
    )

    await message.answer(
        "Выберите должность:",
        reply_markup=role_keyboard,
    )


@router.message(RegisterState.role)
async def input_role(
    message: Message,
    state: FSMContext,
):
    if message.text == "🔧 Наладчик":
        role = UserRole.MECHANIC
    elif message.text == "👷 Оператор":
        role = UserRole.OPERATOR
    else:
        await message.answer(
            "Выберите должность кнопкой."
        )
        return

    await state.update_data(
        role=role
    )

    await state.set_state(
        RegisterState.shift
    )

    await message.answer(
        "Выберите свою смену:",
        reply_markup=shift_keyboard,
    )


@router.message(RegisterState.shift)
async def input_shift(
    message: Message,
    state: FSMContext,
):
    if message.text not in (
        "1",
        "2",
        "3",
        "4",
    ):
        await message.answer(
            "Выберите смену кнопкой."
        )
        return

    data = await state.get_data()

    user = await user_service.create(
        telegram_id=message.from_user.id,
        full_name=data["full_name"],
        role=data["role"],
        shift_number=int(message.text),
    )

    await state.clear()

    await message.answer(
        "✅ Регистрация завершена.\n\n"
        f"ФИО: {user.full_name}\n"
        f"Смена №{user.shift_number}",
        reply_markup=main_keyboard,
    )
