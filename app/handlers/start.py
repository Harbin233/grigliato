from decimal import Decimal, InvalidOperation

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

from app.core.config import settings
from app.models.shift_mechanic import MechanicType
from app.models.user import UserRole
from app.services.machine_service import machine_service
from app.services.production_service import production_service, whole_meters
from app.services.rail_service import rail_service
from app.services.shift_mechanic_service import shift_mechanic_service
from app.services.shift_service import shift_service
from app.services.user_service import user_service
from app.services.work_session_service import work_session_service
from app.states.admin import AdminRailState
from app.states.production import ProductionState
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


def is_admin_id(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


def role_text(role: UserRole) -> str:
    if role == UserRole.ADMIN:
        return "Админ / мастер"
    if role == UserRole.MECHANIC:
        return "Наладчик"
    return "Оператор"


def registration_role_keyboard(allow_admin: bool) -> ReplyKeyboardMarkup:
    buttons = [
        ["🔧 Наладчик"],
        ["👷 Оператор"],
    ]

    if allow_admin:
        buttons.insert(0, ["🛠 Админ / мастер"])

    return keyboard(buttons)


def parse_decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


start_keyboard = keyboard([
    ["▶ Начать регистрацию"],
])

shift_keyboard = keyboard([
    ["1", "2", "3", "4"],
])

main_keyboard = keyboard([
    ["▶ Приступил к работе"],
    ["➕ Добавить продукцию"],
    ["⚙️ Админ режим"],
    ["🕒 Подработка"],
])

admin_keyboard = keyboard([
    ["➕ Добавить рейку"],
    ["↩️ Назад"],
])


def shift_open_keyboard(is_overtime: bool) -> InlineKeyboardMarkup:
    suffix = "1" if is_overtime else "0"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть смену",
                    callback_data=f"open_shift:{suffix}",
                )
            ]
        ]
    )


def mechanic_type_keyboard(is_overtime: bool) -> InlineKeyboardMarkup:
    suffix = "1" if is_overtime else "0"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Основной",
                    callback_data=f"mechanic_type:main:{suffix}",
                ),
                InlineKeyboardButton(
                    text="Вспомогательный",
                    callback_data=f"mechanic_type:assistant:{suffix}",
                ),
            ]
        ]
    )


async def machines_keyboard(is_overtime: bool) -> InlineKeyboardMarkup:
    machines = await machine_service.get_all()
    suffix = "1" if is_overtime else "0"
    rows = []

    for index in range(0, len(machines), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=machine.name,
                    callback_data=f"select_machine:{machine.id}:{suffix}",
                )
                for machine in machines[index:index + 2]
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def production_machines_keyboard() -> InlineKeyboardMarkup:
    machines = await machine_service.get_all()
    rows = []

    for index in range(0, len(machines), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=machine.name,
                    callback_data=f"prod_machine:{machine.id}",
                )
                for machine in machines[index:index + 2]
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def production_rails_keyboard(machine_id: int) -> InlineKeyboardMarkup:
    machine_rails = await production_service.get_enabled_rails_for_machine(
        machine_id
    )
    rows = []

    for machine_rail in machine_rails:
        rows.append(
            [
                InlineKeyboardButton(
                    text=machine_rail.rail.name,
                    callback_data=f"prod_rail:{machine_id}:{machine_rail.id}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def ensure_admin_role(user):
    if user and is_admin_id(user.telegram_id) and user.role != UserRole.ADMIN:
        return await user_service.set_role(user.id, UserRole.ADMIN)
    return user


def mechanic_status_text(mechanic_type: MechanicType) -> str:
    return (
        "основной"
        if mechanic_type == MechanicType.MAIN
        else "вспомогательный"
    )


async def prompt_mechanic_status(
    message: Message,
    active,
    user,
    is_overtime: bool,
) -> None:
    assigned = await shift_mechanic_service.get_by_shift_and_user(
        active.id,
        user.id,
    )

    if assigned:
        overtime_text = "\nПодработка: да" if assigned.is_overtime else ""
        await message.answer(
            "✅ Вы уже отмечены в смене.\n\n"
            f"Смена №{active.shift_number}\n"
            f"Статус: {mechanic_status_text(assigned.mechanic_type)}"
            f"{overtime_text}"
        )
        return

    await message.answer(
        "Выберите статус наладчика в этой смене:",
        reply_markup=mechanic_type_keyboard(is_overtime),
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(
        message.from_user.id
    )
    user = await ensure_admin_role(user)

    if user:
        await state.clear()

        await message.answer(
            f"Добро пожаловать, {user.full_name}.\n\n"
            f"Роль: {role_text(user.role)}\n"
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
    await handle_work_start(message, is_overtime=False)


@router.message(F.text == "🕒 Подработка")
async def start_overtime_work(
    message: Message,
):
    await handle_work_start(message, is_overtime=True)


async def handle_work_start(
    message: Message,
    is_overtime: bool,
):
    user = await user_service.get_by_telegram_id(
        message.from_user.id
    )
    user = await ensure_admin_role(user)

    if user is None:
        await message.answer("Сначала зарегистрируйтесь.")
        return

    active = await shift_service.get_active_shift()

    if active is None:
        if user.role in (UserRole.ADMIN, UserRole.MECHANIC):
            await message.answer(
                "Смена еще не открыта.",
                reply_markup=shift_open_keyboard(is_overtime),
            )
            return

        await message.answer(
            "Смена еще не открыта.\n"
            "Дождитесь наладчика или админа."
        )
        return

    if (
        not is_overtime
        and user.role != UserRole.ADMIN
        and user.shift_number != active.shift_number
    ):
        await message.answer(
            f"Сейчас открыта смена №{active.shift_number}, "
            f"а Ваша смена №{user.shift_number}.\n\n"
            "Если выходите не в свою смену, нажмите «🕒 Подработка»."
        )
        return

    if user.role == UserRole.ADMIN:
        await message.answer(
            "✅ Админ-режим активен.\n\n"
            f"Открыта смена №{active.shift_number}."
        )
        return

    if user.role == UserRole.MECHANIC:
        await prompt_mechanic_status(
            message,
            active,
            user,
            is_overtime,
        )
        return

    active_work = await work_session_service.get_active(user.id)

    if active_work:
        overtime_text = "\nПодработка: да" if active_work.is_overtime else ""
        await message.answer(
            "✅ Вы уже приступили к работе.\n\n"
            f"Станок: {active_work.machine.name}"
            f"{overtime_text}"
        )
        return

    await message.answer(
        "Выберите станок:",
        reply_markup=await machines_keyboard(is_overtime),
    )


@router.message(F.text == "➕ Добавить продукцию")
async def add_production(
    message: Message,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(
        message.from_user.id
    )
    user = await ensure_admin_role(user)

    if user is None:
        await message.answer("Сначала зарегистрируйтесь.")
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await message.answer("Продукцию добавляет наладчик или админ/мастер.")
        return

    active = await shift_service.get_active_shift()

    if active is None:
        await message.answer("Сначала откройте смену.")
        return

    await state.clear()
    await message.answer(
        "Выберите станок для записи продукции:",
        reply_markup=await production_machines_keyboard(),
    )


@router.message(F.text == "⚙️ Админ режим")
async def admin_mode(
    message: Message,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(message.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role != UserRole.ADMIN:
        await message.answer("Админ-режим доступен только админу/мастеру.")
        return

    await state.clear()
    await message.answer(
        "Админ режим.\n\n"
        "Сейчас доступно ведение справочника реек.",
        reply_markup=admin_keyboard,
    )


@router.message(F.text == "↩️ Назад")
async def back_to_main(
    message: Message,
    state: FSMContext,
):
    await state.clear()
    await message.answer(
        "Главное меню.",
        reply_markup=main_keyboard,
    )


@router.message(F.text == "➕ Добавить рейку")
async def add_rail_start(
    message: Message,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(message.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role != UserRole.ADMIN:
        await message.answer("Справочник реек ведет админ/мастер.")
        return

    await state.set_state(AdminRailState.name)
    await message.answer(
        "Введите название рейки.\n\n"
        "Например: GL15 мама 75x75 h37 b15",
        reply_markup=admin_keyboard,
    )


@router.message(AdminRailState.name)
async def admin_rail_name(
    message: Message,
    state: FSMContext,
):
    if not message.text or message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    await state.update_data(name=message.text.strip())
    await state.set_state(AdminRailState.length)
    await message.answer(
        "Введите длину одной штуки в метрах.\n\n"
        "Например: 0.6"
    )


@router.message(AdminRailState.length)
async def admin_rail_length(
    message: Message,
    state: FSMContext,
):
    if message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    length = parse_decimal(message.text or "")

    if length is None or length <= 0:
        await message.answer("Введите длину числом, например 0.6")
        return

    await state.update_data(length=str(length))
    await state.set_state(AdminRailState.pieces_per_pack)
    await message.answer(
        "Введите количество штук в коробке.\n\n"
        "Например: 312"
    )


@router.message(AdminRailState.pieces_per_pack)
async def admin_rail_pieces(
    message: Message,
    state: FSMContext,
):
    if message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите целое число, например 312")
        return

    pieces_per_pack = int(message.text.strip())

    if pieces_per_pack <= 0:
        await message.answer("Количество штук должно быть больше нуля.")
        return

    await state.update_data(pieces_per_pack=pieces_per_pack)
    await state.set_state(AdminRailState.operator_price)
    await message.answer(
        "Введите ставку оператора за 1000 штук.\n\n"
        "Например: 199.18"
    )


@router.message(AdminRailState.operator_price)
async def admin_rail_operator_price(
    message: Message,
    state: FSMContext,
):
    if message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    operator_price = parse_decimal(message.text or "")

    if operator_price is None or operator_price < 0:
        await message.answer("Введите ставку числом, например 199.18")
        return

    await state.update_data(operator_price=str(operator_price))
    await state.set_state(AdminRailState.mechanic_price)
    await message.answer(
        "Введите ставку наладчика за 1000 штук.\n\n"
        "Например: 93.25"
    )


@router.message(AdminRailState.mechanic_price)
async def admin_rail_mechanic_price(
    message: Message,
    state: FSMContext,
):
    if message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    mechanic_price = parse_decimal(message.text or "")

    if mechanic_price is None or mechanic_price < 0:
        await message.answer("Введите ставку числом, например 93.25")
        return

    data = await state.get_data()
    rail = await rail_service.create_with_rates_for_all_machines(
        name=data["name"],
        length=Decimal(data["length"]),
        pieces_per_pack=data["pieces_per_pack"],
        operator_price=Decimal(data["operator_price"]),
        mechanic_price=mechanic_price,
    )

    await state.clear()
    await message.answer(
        "✅ Рейка сохранена.\n\n"
        f"Название: {rail.name}\n"
        f"Длина штуки: {rail.length} м\n"
        f"Штук в коробке: {rail.pieces_per_pack}\n"
        f"Ставка оператора: {data['operator_price']} ₽ / 1000 шт\n"
        f"Ставка наладчика: {mechanic_price} ₽ / 1000 шт\n\n"
        "Ставки применены ко всем активным станкам.",
        reply_markup=admin_keyboard,
    )


@router.callback_query(F.data.startswith("prod_machine:"))
async def select_production_machine(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )
    user = await ensure_admin_role(user)

    if user is None or user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer(
            "Продукцию добавляет наладчик или админ/мастер."
        )
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])
    keyboard_markup = await production_rails_keyboard(machine_id)

    if not keyboard_markup.inline_keyboard:
        await callback.message.answer(
            "Для этого станка пока нет активных реек/ставок."
        )
        await callback.answer()
        return

    await callback.message.answer(
        "Выберите рейку:",
        reply_markup=keyboard_markup,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prod_rail:"))
async def select_production_rail(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )
    user = await ensure_admin_role(user)

    if user is None or user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer(
            "Продукцию добавляет наладчик или админ/мастер."
        )
        await callback.answer()
        return

    _, machine_id_raw, machine_rail_id_raw = callback.data.split(":")

    await state.update_data(
        machine_id=int(machine_id_raw),
        machine_rail_id=int(machine_rail_id_raw),
    )
    await state.set_state(ProductionState.packs)

    await callback.message.answer(
        "Введите количество коробок целым числом:"
    )
    await callback.answer()


@router.message(ProductionState.packs)
async def input_production_packs(
    message: Message,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(
        message.from_user.id
    )
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await message.answer("Продукцию добавляет наладчик или админ/мастер.")
        await state.clear()
        return

    if active is None:
        await message.answer("Смена не открыта.")
        await state.clear()
        return

    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите количество коробок целым числом.")
        return

    packs = int(message.text.strip())

    if packs <= 0:
        await message.answer("Количество коробок должно быть больше нуля.")
        return

    data = await state.get_data()

    try:
        entry, machine, rail, operator_total, mechanic_total = (
            await production_service.create_entry(
                shift=active,
                machine_id=data["machine_id"],
                machine_rail_id=data["machine_rail_id"],
                packs=packs,
                created_by=user,
            )
        )
    except ValueError as error:
        await message.answer(str(error))
        await state.clear()
        return

    await state.clear()

    await message.answer(
        "✅ Продукция добавлена.\n\n"
        f"Смена №{active.shift_number}\n"
        f"Станок: {machine.name}\n"
        f"Рейка: {rail.name}\n"
        f"Коробок: {entry.packs}\n"
        f"Штук: {entry.pieces}\n"
        f"Пог. метров: {whole_meters(Decimal(str(entry.meters)))}\n"
        f"Оператор: {entry.operator_name}\n"
        f"Оператору: {operator_total} ₽\n"
        f"Наладчикам всего: {mechanic_total} ₽"
    )


@router.callback_query(F.data.startswith("open_shift:"))
async def open_shift(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )
    user = await ensure_admin_role(user)

    if user is None:
        await callback.message.answer("Сначала зарегистрируйтесь.")
        await callback.answer()
        return

    is_overtime = callback.data.endswith(":1")
    ok, text = await shift_service.start_shift(
        user,
        allow_overtime=is_overtime,
    )

    await callback.message.answer(text)

    if ok and user.role == UserRole.MECHANIC:
        active = await shift_service.get_active_shift()
        await prompt_mechanic_status(
            callback.message,
            active,
            user,
            is_overtime,
        )

    if ok and user.role == UserRole.ADMIN:
        await callback.message.answer("✅ Админ-режим активен.")

    await callback.answer()


@router.callback_query(F.data.startswith("mechanic_type:"))
async def select_mechanic_type(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )
    user = await ensure_admin_role(user)
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

    _, mechanic_type_raw, overtime_raw = callback.data.split(":")
    mechanic_type = (
        MechanicType.MAIN
        if mechanic_type_raw == "main"
        else MechanicType.ASSISTANT
    )
    is_overtime = overtime_raw == "1"

    existing = await shift_mechanic_service.get_by_shift_and_user(
        active.id,
        user.id,
    )

    if mechanic_type == MechanicType.MAIN:
        main_count = await shift_mechanic_service.count_main(
            active.id,
            exclude_user_id=user.id,
        )

        if (
            existing is None
            or existing.mechanic_type != MechanicType.MAIN
        ) and main_count >= 2:
            await callback.message.answer(
                "В смене уже отмечены два основных наладчика."
            )
            await callback.answer()
            return

    await shift_mechanic_service.assign(
        active.id,
        user.id,
        mechanic_type,
        is_overtime=is_overtime,
    )

    overtime_text = "\nПодработка: да" if is_overtime else ""

    await callback.message.answer(
        "✅ Статус наладчика сохранен.\n\n"
        f"Смена №{active.shift_number}\n"
        f"Статус: {mechanic_status_text(mechanic_type)}"
        f"{overtime_text}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_machine:"))
async def select_machine(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer(
            "Смена не найдена. Нажмите /start и попробуйте снова."
        )
        await callback.answer()
        return

    if user.role != UserRole.OPERATOR:
        await callback.message.answer("Станок выбирает оператор.")
        await callback.answer()
        return

    _, machine_id_raw, overtime_raw = callback.data.split(":")
    is_overtime = overtime_raw == "1"

    if (
        not is_overtime
        and user.shift_number != active.shift_number
    ):
        await callback.message.answer(
            f"Сейчас открыта смена №{active.shift_number}, "
            f"а Ваша смена №{user.shift_number}.\n\n"
            "Если выходите не в свою смену, нажмите «🕒 Подработка»."
        )
        await callback.answer()
        return

    ok, text = await work_session_service.start(
        user,
        active,
        int(machine_id_raw),
        is_overtime=is_overtime,
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

    await message.answer("Введите Ваше ФИО.")


@router.message(RegisterState.full_name)
async def input_name(
    message: Message,
    state: FSMContext,
):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(RegisterState.role)

    await message.answer(
        "Выберите должность:",
        reply_markup=registration_role_keyboard(
            is_admin_id(message.from_user.id)
        ),
    )


@router.message(RegisterState.role)
async def input_role(
    message: Message,
    state: FSMContext,
):
    if message.text == "🛠 Админ / мастер" and is_admin_id(message.from_user.id):
        role = UserRole.ADMIN
    elif message.text == "🔧 Наладчик":
        role = UserRole.MECHANIC
    elif message.text == "👷 Оператор":
        role = UserRole.OPERATOR
    else:
        await message.answer("Выберите должность кнопкой.")
        return

    await state.update_data(role=role)
    await state.set_state(RegisterState.shift)

    await message.answer(
        "Выберите свою смену:",
        reply_markup=shift_keyboard,
    )


@router.message(RegisterState.shift)
async def input_shift(
    message: Message,
    state: FSMContext,
):
    if message.text not in ("1", "2", "3", "4"):
        await message.answer("Выберите смену кнопкой.")
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
        f"Роль: {role_text(user.role)}\n"
        f"Смена №{user.shift_number}",
        reply_markup=main_keyboard,
    )
