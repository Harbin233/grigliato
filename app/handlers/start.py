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
from app.models.shift_mechanic import MechanicType
from app.services.machine_service import machine_service
from app.services.shift_mechanic_service import shift_mechanic_service
from app.services.shift_service import shift_service
from app.services.user_service import user_service
from app.services.work_session_service import work_session_service
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


mechanic_type_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Основной",
                callback_data="mechanic_type:main",
            ),
            InlineKeyboardButton(
                text="Вспомогательный",
                callback_data="mechanic_type:assistant",
            ),
        ]
    ]
)


async def machines_keyboard() -> InlineKeyboardMarkup:
    machines = await machine_service.get_all()
    rows = []

    for index in range(0, len(machines), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=machine.name,
                    callback_data=f"select_machine:{machine.id}",
                )
                for machine in machines[index:index + 2]
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


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

    if user.role == UserRole.MECHANIC:
        assigned = await shift_mechanic_service.get_by_shift_and_user(
            active.id,
            user.id,
        )

        if assigned:
            mechanic_type_text = (
                "основной"
                if assigned.mechanic_type == MechanicType.MAIN
                else "вспомогательный"
            )
            await message.answer(
                "✅ Вы уже отмечены в смене.\n\n"
                f"Смена №{active.shift_number}\n"
                f"Статус: {mechanic_type_text}"
            )
            return

        await message.answer(
            "Выберите статус наладчика в этой смене:",
            reply_markup=mechanic_type_keyboard,
        )
        return

    active_work = await work_session_service.get_active(user.id)

    if active_work:
        await message.answer(
            "✅ Вы уже приступили к работе.\n\n"
            f"Станок: {active_work.machine.name}"
        )
        return

    await message.answer(
        "Выберите станок:",
        reply_markup=await machines_keyboard(),
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

    if ok:
        await callback.message.answer(
            "Выберите статус наладчика в этой смене:",
            reply_markup=mechanic_type_keyboard,
        )

    await callback.answer()


@router.callback_query(F.data.startswith("mechanic_type:"))
async def select_mechanic_type(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer(
            "Смена не найдена. Нажмите /start и попробуйте снова."
        )
        await callback.answer()
        return

    if user.role != UserRole.MECHANIC:
        await callback.message.answer(
            "Этот выбор доступен только наладчикам."
        )
        await callback.answer()
        return

    mechanic_type = (
        MechanicType.MAIN
        if callback.data.endswith(":main")
        else MechanicType.ASSISTANT
    )

    if mechanic_type == MechanicType.MAIN:
        existing = await shift_mechanic_service.get_by_shift_and_user(
            active.id,
            user.id,
        )
        main_count = await shift_mechanic_service.count_main(active.id)

        if existing is None and main_count >= 2:
            await callback.message.answer(
                "В смене уже отмечены два основных наладчика."
            )
            await callback.answer()
            return

    await shift_mechanic_service.assign(
        active.id,
        user.id,
        mechanic_type,
    )

    mechanic_type_text = (
        "основной"
        if mechanic_type == MechanicType.MAIN
        else "вспомогательный"
    )

    await callback.message.answer(
        "✅ Статус наладчика сохранен.\n\n"
        f"Смена №{active.shift_number}\n"
        f"Статус: {mechanic_type_text}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_machine:"))
async def select_machine(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer(
            "Смена не найдена. Нажмите /start и попробуйте снова."
        )
        await callback.answer()
        return

    if user.role != UserRole.OPERATOR:
        await callback.message.answer(
            "Станок выбирает оператор."
        )
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])

    ok, text = await work_session_service.start(
        user,
        active,
        machine_id,
    )

    await callback.message.answer(
        ("✅ " if ok else "⚠️ ") + text
    )
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
