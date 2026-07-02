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


RAIL_CLASSES = {
    "Эконом": ["Мама", "Папа"],
    "GL": ["Мама", "Папа", "L"],
}

RAIL_SHAPE_CODES = {
    "mama": "Мама",
    "papa": "Папа",
    "l": "L",
}


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
    ["➕ Записать продукцию"],
    ["📚 Справочник реек"],
    ["⚙️ Админ режим"],
    ["🕒 Подработка"],
])

admin_keyboard = keyboard([
    ["➕ Добавить рейку"],
    ["↩️ Назад"],
])

admin_skip_keyboard = keyboard([
    ["⏭ Пропустить"],
    ["↩️ Назад"],
])

rail_class_keyboard = keyboard([
    ["Эконом", "GL"],
    ["↩️ Назад"],
])


def rail_shape_keyboard(rail_class: str) -> ReplyKeyboardMarkup:
    shapes = RAIL_CLASSES[rail_class]
    rows = [[shape] for shape in shapes]
    rows.append(["Все виды"])
    rows.append(["↩️ Назад"])

    return keyboard(rows)


def rail_base_name_prompt(rail_class: str) -> str:
    if rail_class == "GL":
        return (
            "Введите модель или размер без класса GL и без вида рейки.\n\n"
            "Это ручное поле: можно ввести любую новую ячейку/размер.\n\n"
            "Например: 15 75x75 h37 b15\n"
            "или: 75x75 h37 b15"
        )

    return (
        "Введите модель или размер без класса Эконом и без вида рейки.\n\n"
        "Это ручное поле: можно ввести любую новую ячейку/размер.\n\n"
        "Например: 50x40x10\n"
        "или: 60x40x10"
    )


def rails_list_text(rails, limit: int = 20) -> str:
    if not rails:
        return "Пока нет заведённых реек."

    lines = [f"- {rail.name}" for rail in rails[:limit]]

    if len(rails) > limit:
        lines.append(f"...и ещё {len(rails) - limit}")

    return "\n".join(lines)


def rail_name(rail_class: str, rail_shape: str, base_name: str) -> str:
    return f"{rail_class} {rail_shape} {base_name}"


def split_rail_name(name: str) -> tuple[str, str, str] | None:
    parts = name.split(" ", maxsplit=2)

    if len(parts) != 3:
        return None

    return parts[0], parts[1], parts[2]


def related_rail_shapes(rail_class: str, rail_shape: str) -> list[str]:
    return [
        shape
        for shape in RAIL_CLASSES.get(rail_class, [])
        if shape != rail_shape
    ]


def shape_code(rail_shape: str) -> str:
    for code, shape in RAIL_SHAPE_CODES.items():
        if shape == rail_shape:
            return code

    raise ValueError(f"Unknown rail shape: {rail_shape}")


def create_related_shapes_keyboard(
    source_rail_id: int,
    missing_shapes: list[str],
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Создать {shape} с теми же параметрами",
                    callback_data=(
                        f"rail_clone:{source_rail_id}:{shape_code(shape)}"
                    ),
                )
            ]
            for shape in missing_shapes
        ]
    )


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


async def production_all_rails_keyboard() -> InlineKeyboardMarkup:
    rails = await production_service.get_enabled_rails()
    rows = []

    for rail in rails:
        rows.append(
            [
                InlineKeyboardButton(
                    text=rail.name,
                    callback_data=f"prod_rail_first:{rail.id}",
                )
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


async def production_machines_for_rail_keyboard(
    rail_id: int,
) -> InlineKeyboardMarkup:
    machine_rails = await production_service.get_enabled_machines_for_rail(
        rail_id
    )
    rows = []

    for index in range(0, len(machine_rails), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=machine_rail.machine.name,
                    callback_data=(
                        "prod_machine_for_rail:"
                        f"{machine_rail.machine_id}:{machine_rail.id}"
                    ),
                )
                for machine_rail in machine_rails[index:index + 2]
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_machine_rate(text: str) -> tuple[Decimal, Decimal] | None:
    parts = text.replace(";", " ").replace(",", ".").split()

    if len(parts) != 2:
        return None

    operator_price = parse_decimal(parts[0])
    mechanic_price = parse_decimal(parts[1])

    if (
        operator_price is None
        or mechanic_price is None
        or operator_price < 0
        or mechanic_price < 0
    ):
        return None

    return operator_price, mechanic_price


async def prompt_next_machine_rate(
    message: Message,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    machines = data["machines"]
    machine_index = data["machine_index"]

    if machine_index >= len(machines):
        await finish_admin_rail(message, state)
        return

    machine = machines[machine_index]
    await state.set_state(AdminRailState.machine_rate)
    await message.answer(
        f"Станок: {machine['name']}\n\n"
        "Введите ставки за 1000 штук через пробел:\n"
        "оператор наладчик\n\n"
        "Например: 199.18 93.25\n\n"
        "Если на этом станке рейка не производится, нажмите "
        "«⏭ Пропустить».",
        reply_markup=admin_skip_keyboard,
    )


async def finish_admin_rail(
    message: Message,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    rail_names = [
        f"{data['rail_class']} {shape} {data['name']}"
        for shape in data["rail_shapes"]
    ]
    machine_rates = [
        {
            "machine_id": rate["machine_id"],
            "operator_price": Decimal(rate["operator_price"]),
            "mechanic_price": Decimal(rate["mechanic_price"]),
        }
        for rate in data["machine_rates"]
    ]

    rails = []

    for rail_name in rail_names:
        rails.append(
            await rail_service.create_with_rates_for_all_machines(
                name=rail_name,
                length=Decimal(data["length"]),
                pieces_per_pack=data["pieces_per_pack"],
                machine_rates=machine_rates,
            )
        )

    enabled_count = len(data["machine_rates"])
    skipped_count = len(data["machines"]) - enabled_count
    names_text = "\n".join(f"- {rail.name}" for rail in rails)
    missing_shapes = []

    if len(rails) == 1:
        rail_parts = split_rail_name(rails[0].name)

        if rail_parts:
            rail_class, rail_shape, base_name = rail_parts
            for shape in related_rail_shapes(rail_class, rail_shape):
                related_name = rail_name(rail_class, shape, base_name)
                existing_related = await rail_service.get_by_name(related_name)

                if existing_related is None:
                    missing_shapes.append(shape)

    await state.clear()
    await message.answer(
        "✅ Рейки сохранены.\n\n"
        f"{names_text}\n\n"
        f"Длина штуки: {rails[0].length} м\n"
        f"Штук в коробке: {rails[0].pieces_per_pack}\n"
        f"Станков с ценой: {enabled_count}\n"
        f"Пропущено станков: {skipped_count}",
        reply_markup=admin_keyboard,
    )

    if missing_shapes:
        await message.answer(
            "Можно сразу добавить связанные виды с теми же параметрами.",
            reply_markup=create_related_shapes_keyboard(
                rails[0].id,
                missing_shapes,
            ),
        )


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


@router.message(F.text == "➕ Записать продукцию")
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
    keyboard_markup = await production_all_rails_keyboard()

    if not keyboard_markup.inline_keyboard:
        await message.answer(
            "В справочнике пока нет активных реек со ставками.\n\n"
            "Откройте «📚 Справочник реек» и добавьте рейку."
        )
        return

    await message.answer(
        "Выберите рейку для записи продукции:",
        reply_markup=keyboard_markup,
    )


@router.message(F.text == "📚 Справочник реек")
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
    rails = await rail_service.get_all()
    await message.answer(
        "Админ режим.\n\n"
        "Здесь добавляются новые рейки и ставки по станкам.\n\n"
        "Уже заведено:\n"
        f"{rails_list_text(rails)}",
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

    await state.set_state(AdminRailState.rail_class)
    await message.answer(
        "Выберите класс рейки:",
        reply_markup=rail_class_keyboard,
    )


@router.message(AdminRailState.rail_class)
async def admin_rail_class(
    message: Message,
    state: FSMContext,
):
    if not message.text or message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    rail_class = message.text.strip()

    if rail_class not in RAIL_CLASSES:
        await message.answer(
            "Выберите класс рейки кнопкой.",
            reply_markup=rail_class_keyboard,
        )
        return

    existing_rails = await rail_service.get_by_class(rail_class)
    await state.update_data(rail_class=rail_class)
    await state.set_state(AdminRailState.rail_shapes)
    await message.answer(
        "Выберите вид рейки.\n\n"
        "Если цены одинаковые для всех видов, нажмите «Все виды».\n\n"
        f"Уже есть {rail_class}:\n"
        f"{rails_list_text(existing_rails)}",
        reply_markup=rail_shape_keyboard(rail_class),
    )


@router.message(AdminRailState.rail_shapes)
async def admin_rail_shapes(
    message: Message,
    state: FSMContext,
):
    if not message.text or message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    data = await state.get_data()
    rail_class = data["rail_class"]
    available_shapes = RAIL_CLASSES[rail_class]
    selected = message.text.strip()

    if selected == "Все виды":
        rail_shapes = available_shapes
    elif selected in available_shapes:
        rail_shapes = [selected]
    else:
        await message.answer(
            "Выберите вид рейки кнопкой.",
            reply_markup=rail_shape_keyboard(rail_class),
        )
        return

    await state.update_data(rail_shapes=rail_shapes)
    await state.set_state(AdminRailState.name)
    await message.answer(
        rail_base_name_prompt(rail_class),
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

    base_name = message.text.strip()
    data = await state.get_data()
    rail_shapes = data["rail_shapes"]
    existing_target_rails = []

    for rail_shape in rail_shapes:
        target_name = rail_name(
            data["rail_class"],
            rail_shape,
            base_name,
        )
        existing_rail = await rail_service.get_by_name(target_name)

        if existing_rail:
            existing_target_rails.append(existing_rail)

    if existing_target_rails:
        await message.answer(
            "Такая рейка уже есть в справочнике:\n"
            f"{rails_list_text(existing_target_rails)}\n\n"
            "Введите другой размер/модель или выберите другой вид рейки.",
            reply_markup=admin_keyboard,
        )
        return

    if len(rail_shapes) == 1:
        rail_shape = rail_shapes[0]

        for related_shape in related_rail_shapes(data["rail_class"], rail_shape):
            related_name = rail_name(
                data["rail_class"],
                related_shape,
                base_name,
            )
            existing_related = await rail_service.get_by_name(related_name)

            if existing_related:
                rail = await rail_service.clone_shape_from_source(
                    existing_related.id,
                    rail_shape,
                )
                await state.clear()

                if rail is None:
                    await message.answer(
                        "Не получилось скопировать связанную рейку. "
                        "Попробуйте добавить вручную.",
                        reply_markup=admin_keyboard,
                    )
                    return

                await message.answer(
                    "✅ Рейка создана из связанного вида "
                    "без повторного ввода цен.\n\n"
                    f"Источник: {existing_related.name}\n"
                    f"Создано: {rail.name}",
                    reply_markup=admin_keyboard,
                )
                return

    await state.update_data(name=base_name)
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

    machines = await machine_service.get_all()

    if not machines:
        await message.answer("Нет активных станков для назначения цен.")
        await state.clear()
        return

    await state.update_data(
        pieces_per_pack=pieces_per_pack,
        machines=[
            {
                "id": machine.id,
                "name": machine.name,
            }
            for machine in machines
        ],
        machine_index=0,
        machine_rates=[],
    )
    await prompt_next_machine_rate(message, state)


@router.message(AdminRailState.machine_rate)
async def admin_rail_machine_rate(
    message: Message,
    state: FSMContext,
):
    if message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    data = await state.get_data()
    machines = data["machines"]
    machine_index = data["machine_index"]

    if message.text == "⏭ Пропустить":
        await state.update_data(machine_index=machine_index + 1)
        await prompt_next_machine_rate(message, state)
        return

    prices = parse_machine_rate(message.text or "")

    if prices is None:
        await message.answer(
            "Введите две ставки через пробел, например 199.18 93.25,\n"
            "или нажмите «⏭ Пропустить»."
        )
        return

    operator_price, mechanic_price = prices
    machine_rates = data["machine_rates"]
    machine_rates.append(
        {
            "machine_id": machines[machine_index]["id"],
            "operator_price": str(operator_price),
            "mechanic_price": str(mechanic_price),
        }
    )

    await state.update_data(
        machine_index=machine_index + 1,
        machine_rates=machine_rates,
    )
    await prompt_next_machine_rate(message, state)


@router.callback_query(F.data.startswith("rail_clone:"))
async def create_related_rail_shape(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role != UserRole.ADMIN:
        await callback.message.answer("Справочник реек ведет админ/мастер.")
        await callback.answer()
        return

    _, source_rail_id_raw, shape_code_raw = callback.data.split(":")
    rail_shape = RAIL_SHAPE_CODES.get(shape_code_raw)

    if rail_shape is None:
        await callback.message.answer("Неизвестный вид рейки.")
        await callback.answer()
        return

    source_rail_id = int(source_rail_id_raw)
    rail = await rail_service.clone_shape_from_source(
        source_rail_id,
        rail_shape,
    )

    if rail is None:
        await callback.message.answer(
            "Не получилось создать связанную рейку. "
            "Проверьте название исходной рейки."
        )
        await callback.answer()
        return

    await callback.message.answer(
        "✅ Рейка создана с теми же параметрами и ставками.\n\n"
        f"Создано: {rail.name}",
        reply_markup=admin_keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rail_pair:"))
async def create_rail_pair(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role != UserRole.ADMIN:
        await callback.message.answer("Справочник реек ведет админ/мастер.")
        await callback.answer()
        return

    source_rail_id = int(callback.data.split(":", maxsplit=1)[1])
    rail = await rail_service.clone_pair_from_source(source_rail_id)

    if rail is None:
        await callback.message.answer(
            "Не получилось создать парную рейку. "
            "Проверьте название исходной рейки."
        )
        await callback.answer()
        return

    await callback.message.answer(
        "✅ Парная рейка создана с теми же параметрами и ставками.\n\n"
        f"Создано: {rail.name}",
        reply_markup=admin_keyboard,
    )
    await callback.answer()


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


@router.callback_query(F.data.startswith("prod_rail_first:"))
async def select_production_rail_first(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )
    user = await ensure_admin_role(user)

    if user is None or user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer(
            "Продукцию записывает наладчик или админ/мастер."
        )
        await callback.answer()
        return

    rail_id = int(callback.data.split(":", maxsplit=1)[1])
    keyboard_markup = await production_machines_for_rail_keyboard(rail_id)

    if not keyboard_markup.inline_keyboard:
        await callback.message.answer(
            "Для этой рейки пока нет активных ставок по станкам."
        )
        await callback.answer()
        return

    await callback.message.answer(
        "Выберите станок:",
        reply_markup=keyboard_markup,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prod_machine_for_rail:"))
async def select_production_machine_for_rail(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(
        callback.from_user.id
    )
    user = await ensure_admin_role(user)

    if user is None or user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer(
            "Продукцию записывает наладчик или админ/мастер."
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
