import re
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
from app.services.active_machine_rail_service import active_machine_rail_service
from app.services.machine_service import machine_service
from app.services.production_service import production_service, whole_meters
from app.services.rail_service import rail_service
from app.services.shift_machine_service import shift_machine_service
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
    "Эконом": ["Мама", "Папа", "Напр"],
    "GL15": ["Мама", "Папа", "L"],
    "Grigliato": ["Мама", "Папа", "Напр"],
    "Пирамида": ["Мама", "Папа", "Напр"],
}

RAIL_PRICE_GROUPS = {
    "Эконом": [
        ["Мама", "Папа"],
        ["Напр"],
    ],
    "GL15": [
        ["Мама", "Папа", "L"],
    ],
    "Grigliato": [
        ["Мама", "Папа"],
        ["Напр"],
    ],
    "Пирамида": [
        ["Мама", "Папа"],
        ["Напр"],
    ],
}

RAIL_SHAPE_CODES = {
    "mama": "Мама",
    "papa": "Папа",
    "napr": "Напр",
    "l": "L",
}

ECONOM_GUIDE_LENGTHS = ["0.6", "1.2", "2.40"]
KNOWN_RAIL_CLASSES = ["Эконом", "GL15", "Grigliato", "Пирамида"]
KNOWN_RAIL_SHAPES = ["Мама", "Папа", "Напр", "L"]
RAIL_GROUP_FIELDS = ["rail_class", "shape", "guide_length", "cell", "h", "b"]


class RailInfo(dict):
    pass


def parse_decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def parse_mechanic_operator_rate(text: str) -> tuple[Decimal, Decimal] | None:
    parts = text.replace(";", " ").replace(",", ".").split()

    if len(parts) != 2:
        return None

    mechanic_price = parse_decimal(parts[0])
    operator_price = parse_decimal(parts[1])

    if (
        mechanic_price is None
        or operator_price is None
        or mechanic_price < 0
        or operator_price < 0
    ):
        return None

    return mechanic_price, operator_price


start_keyboard = keyboard([
    ["▶ Начать регистрацию"],
])

shift_keyboard = keyboard([
    ["1", "2", "3", "4"],
])

main_keyboard = keyboard([
    ["▶ Приступил к работе"],
    ["🛠 Мои станки"],
    ["👥 Люди смены"],
    ["➕ Записать продукцию"],
    ["🧮 Тестовый просчет"],
    ["✅ Закрыть смену"],
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

econom_guide_length_keyboard = keyboard([
    ["0.6", "1.2", "2.40"],
    ["↩️ Назад"],
])

rail_class_keyboard = keyboard([
    ["Эконом", "GL15"],
    ["Grigliato", "Пирамида"],
    ["↩️ Назад"],
])


def rail_shape_keyboard(rail_class: str) -> ReplyKeyboardMarkup:
    shapes = RAIL_CLASSES[rail_class]
    rows = [[shape] for shape in shapes]

    if "Напр" in shapes:
        rows.append(["Мама + Папа"])
    else:
        rows.append(["Все виды"])

    rows.append(["↩️ Назад"])

    return keyboard(rows)


def rail_base_name_prompt(rail_class: str) -> str:
    if rail_class == "GL15":
        return (
            "Введите модель или размер без класса GL15 и без вида рейки.\n\n"
            "Это ручное поле: можно ввести любую новую ячейку/размер.\n\n"
            "Например: 75x75 h37 b15\n"
            "или: 75x75 h37 b15"
        )

    return (
        "Введите модель или размер без класса Эконом и без вида рейки.\n\n"
        "Это ручное поле: можно ввести любую новую ячейку/размер.\n\n"
        "Например: 50x40x10\n"
        "или: направляющая 40x20"
    )


def rails_list_text(rails, limit: int = 20) -> str:
    if not rails:
        return "Пока нет заведённых реек."

    lines = [f"- {rail.name}" for rail in rails[:limit]]

    if len(rails) > limit:
        lines.append(f"...и ещё {len(rails) - limit}")

    return "\n".join(lines)


def parse_catalog_rail(rail) -> RailInfo | None:
    name = rail.name
    parts = name.split()
    shape = "Без вида"

    if not parts or parts[0] not in KNOWN_RAIL_CLASSES:
        return None

    rail_class = parts[0]
    offset = 1

    if len(parts) > offset and parts[offset] in KNOWN_RAIL_SHAPES:
        shape = parts[offset]
        offset += 1

    base_parts = parts[offset:]
    guide_length = ""

    if shape == "Напр" and base_parts and base_parts[-1].endswith("м"):
        guide_length = base_parts[-1].removesuffix("м")
        base_parts = base_parts[:-1]

    base_name = " ".join(base_parts) if base_parts else name
    cell_match = re.search(r"\d+x\d+", base_name)
    h_match = re.search(r"\bh\d+\b", base_name)
    b_match = re.search(r"\bb\d+\b", base_name)

    return RailInfo(
        rail=rail,
        rail_class=rail_class,
        shape=shape,
        guide_length=guide_length,
        cell=cell_match.group(0) if cell_match else "Без ячейки",
        h=h_match.group(0) if h_match else "Без h",
        b=b_match.group(0) if b_match else "Без b",
        base_name=base_name,
    )


def filter_rail_infos(infos: list[RailInfo], filters: dict) -> list[RailInfo]:
    return [
        info
        for info in infos
        if all(info.get(field) == value for field, value in filters.items())
    ]


def next_group_field(infos: list[RailInfo], filters: dict) -> str | None:
    filtered = filter_rail_infos(infos, filters)

    for field in RAIL_GROUP_FIELDS:
        if field in filters:
            continue

        values = sorted({info.get(field, "") for info in filtered})

        if len(values) > 1:
            return field

        if len(values) == 1:
            filters[field] = values[0]

    return None


def group_field_title(field: str) -> str:
    return {
        "rail_class": "Выберите тип рейки:",
        "shape": "Выберите вид рейки:",
        "guide_length": "Выберите длину направляющей:",
        "cell": "Выберите ячейку:",
        "h": "Выберите высоту:",
        "b": "Выберите b:",
    }.get(field, "Выберите:")


def navigation_rows(prefix: str, show_back: bool) -> list[list[InlineKeyboardButton]]:
    buttons = []

    if show_back:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"{prefix}:back",
            )
        )

    buttons.append(
        InlineKeyboardButton(
            text="🏠 Сначала",
            callback_data=f"{prefix}:reset",
        )
    )

    return [buttons]


def action_navigation_row(
    *buttons: tuple[str, str],
) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text=text, callback_data=callback_data)
        for text, callback_data in buttons
    ]


def with_action_navigation(
    rows: list[list[InlineKeyboardButton]],
    *buttons: tuple[str, str],
) -> InlineKeyboardMarkup:
    if buttons:
        rows.append(action_navigation_row(*buttons))

    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_keyboard(
    prefix: str,
    field: str,
    values: list[str],
    show_back: bool,
) -> InlineKeyboardMarkup:
    rows = []

    for index in range(0, len(values), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=value,
                    callback_data=f"{prefix}:{field}:{index + offset}",
                )
                for offset, value in enumerate(values[index:index + 2])
            ]
        )

    rows.extend(navigation_rows(prefix, show_back))

    return InlineKeyboardMarkup(inline_keyboard=rows)


def rails_keyboard(
    prefix: str,
    infos: list[RailInfo],
    navigation_prefix: str,
    show_back: bool,
) -> InlineKeyboardMarkup:
    rows = []

    for info in infos:
        rail = info["rail"]
        rows.append(
            [
                InlineKeyboardButton(
                    text=rail.name,
                    callback_data=f"{prefix}:{rail.id}",
                )
            ]
        )

    rows.extend(navigation_rows(navigation_prefix, show_back))

    return InlineKeyboardMarkup(inline_keyboard=rows)


def production_rail_confirm_keyboard(
    rail_id: int,
    callback_prefix: str,
    back_callback: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅",
                    callback_data=f"{callback_prefix}:{rail_id}",
                ),
                InlineKeyboardButton(
                    text="❌",
                    callback_data=back_callback,
                ),
            ]
        ]
    )


async def send_grouped_rails_step(
    message,
    state: FSMContext,
    *,
    mode: str,
    rails,
) -> None:
    infos = [
        info
        for rail in rails
        if (info := parse_catalog_rail(rail)) is not None
    ]
    state_key = f"{mode}_filters"
    values_key = f"{mode}_values"
    history_key = f"{mode}_history"
    prefixes = {
        "prod": "prodsel",
        "cat": "catsel",
        "mprod": "mprodsel",
        "test": "testsel",
    }
    rail_prefixes = {
        "prod": "prod_rail_first",
        "cat": "catrail",
        "mprod": "mprod_rail",
        "test": "test_rail_first",
    }
    prefix = prefixes[mode]
    rail_prefix = rail_prefixes[mode]
    data = await state.get_data()
    filters = dict(data.get(state_key, {}))
    history = data.get(history_key, [])
    filtered = filter_rail_infos(infos, filters)

    if not filtered:
        await message.answer("По выбранным параметрам рейки не найдены.")
        return

    field = next_group_field(infos, filters)

    if field is None:
        if mode in ("prod", "mprod", "test") and len(filtered) == 1:
            rail = filtered[0]["rail"]
            confirm_prefix = (
                "prod_confirm_rail"
                if mode == "prod"
                else "mprod_confirm_rail"
                if mode == "mprod"
                else "test_confirm_rail"
            )
            await message.answer(
                "Все верно?\n\n"
                f"{rail.name}",
                reply_markup=production_rail_confirm_keyboard(
                    rail.id,
                    confirm_prefix,
                    f"{prefix}:back",
                ),
            )
            await state.update_data(**{state_key: filters, values_key: []})
            return

        await message.answer(
            "Выберите рейку:",
            reply_markup=rails_keyboard(
                rail_prefix,
                filtered,
                prefix,
                bool(history),
            ),
        )
        await state.update_data(**{state_key: filters, values_key: []})
        return

    filtered = filter_rail_infos(infos, filters)
    values = sorted({info[field] for info in filtered})
    await state.update_data(**{state_key: filters, values_key: values})
    await message.answer(
        group_field_title(field),
        reply_markup=group_keyboard(prefix, field, values, bool(history)),
    )


def rail_name(rail_class: str, rail_shape: str, base_name: str) -> str:
    return f"{rail_class} {rail_shape} {base_name}"


def catalog_rail_name(
    rail_class: str,
    rail_shape: str,
    base_name: str,
    length: str | None = None,
) -> str:
    if rail_shape == "Напр" and length:
        return f"{rail_class} {rail_shape} {base_name} {length}м"

    return rail_name(rail_class, rail_shape, base_name)


def split_rail_name(name: str) -> tuple[str, str, str] | None:
    parts = name.split(" ", maxsplit=2)

    if len(parts) != 3:
        return None

    return parts[0], parts[1], parts[2]


def related_rail_shapes(rail_class: str, rail_shape: str) -> list[str]:
    for group in RAIL_PRICE_GROUPS.get(rail_class, []):
        if rail_shape in group:
            return [
                shape
                for shape in group
                if shape != rail_shape
            ]

    return []


def shape_code(rail_shape: str) -> str:
    for code, shape in RAIL_SHAPE_CODES.items():
        if shape == rail_shape:
            return code

    raise ValueError(f"Unknown rail shape: {rail_shape}")


def create_related_shapes_keyboard(
    source_rail_id: int,
    missing_shapes: list[str],
) -> InlineKeyboardMarkup:
    rows = [
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

    return with_action_navigation(
        rows,
        ("↩️ В справочник", "nav:admin_start"),
    )


def shift_open_keyboard(is_overtime: bool) -> InlineKeyboardMarkup:
    suffix = "1" if is_overtime else "0"
    return with_action_navigation(
        [
            [
                InlineKeyboardButton(
                    text="🚀 Открыть смену",
                    callback_data=f"open_shift:{suffix}",
                )
            ]
        ],
        ("↩️ В меню", "nav:main"),
    )


def mechanic_type_keyboard(is_overtime: bool) -> InlineKeyboardMarkup:
    suffix = "1" if is_overtime else "0"
    return with_action_navigation(
        [
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
        ],
        ("↩️ В меню", "nav:main"),
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

    return with_action_navigation(
        rows,
        ("↩️ В меню", "nav:main"),
    )


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

    return with_action_navigation(
        rows,
        ("↩️ В меню", "nav:main"),
    )


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

    return with_action_navigation(
        rows,
        ("↩️ В меню", "nav:main"),
    )


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

    return with_action_navigation(
        rows,
        ("⬅️ Назад", "nav:production_start"),
        ("↩️ В меню", "nav:main"),
    )


def frequent_rails_keyboard(
    machine_id: int,
    frequent_rails,
    *,
    choose_callback: str,
    catalog_callback: str,
    back_callback: str,
) -> InlineKeyboardMarkup:
    rows = []

    for machine_rail, entries_count, packs_count in frequent_rails:
        if choose_callback == "prod_freq_rail":
            callback_data = f"{choose_callback}:{machine_id}:{machine_rail.id}"
        else:
            callback_data = f"{choose_callback}:{machine_rail.rail_id}"

        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{machine_rail.rail.name} "
                        f"({entries_count} раз / {packs_count} кор.)"
                    ),
                    callback_data=callback_data,
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="📚 Выбрать из справочника",
                callback_data=f"{catalog_callback}:{machine_id}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=back_callback,
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def production_machines_for_rail_keyboard(
    rail_id: int,
    callback_prefix: str = "prod_machine_for_rail",
    back_callback: str = "nav:prod_current",
    reset_callback: str = "prodsel:reset",
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
                        f"{callback_prefix}:"
                        f"{machine_rail.machine_id}:{machine_rail.id}"
                    ),
                )
                for machine_rail in machine_rails[index:index + 2]
            ]
        )

    return with_action_navigation(
        rows,
        ("⬅️ К рейкам", back_callback),
        ("🏠 Сначала", reset_callback),
    )


def my_machines_keyboard(assignments) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=assignment.machine.name,
                callback_data=f"my_machine:{assignment.machine_id}",
            )
        ]
        for assignment in assignments
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Взять станок",
                callback_data="my_machine_take",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ В меню",
                callback_data="nav:main",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def take_machines_keyboard(
    machines,
    assignments,
    user_id: int,
) -> InlineKeyboardMarkup:
    assigned_by_machine = {
        assignment.machine_id: assignment
        for assignment in assignments
    }
    rows = []

    for index in range(0, len(machines), 2):
        row = []

        for machine in machines[index:index + 2]:
            assignment = assigned_by_machine.get(machine.id)

            if assignment is None:
                text = f"➕ {machine.name}"
                callback_data = f"assign_machine:{machine.id}"
            elif assignment.user_id == user_id:
                text = f"✅ {machine.name}"
                callback_data = f"unassign_machine:{machine.id}"
            else:
                text = f"👤 {machine.name}"
                callback_data = f"taken_machine:{machine.id}"

            row.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data=callback_data,
                )
            )

        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Мои станки",
                callback_data="my_machines",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_machine_panel_keyboard(machine_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Поставить/сменить рейку",
                    callback_data=f"myprod_start:{machine_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Завершить рейку",
                    callback_data=f"finish_active_rail:{machine_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Убрать рейку без отчёта",
                    callback_data=f"clear_active_rail:{machine_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Что уже внесено",
                    callback_data=f"my_machine_summary:{machine_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➖ Убрать из моих",
                    callback_data=f"unassign_machine:{machine_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Мои станки",
                    callback_data="my_machines",
                )
            ],
        ]
    )


async def my_machine_panel_text(machine, active) -> str:
    active_rail = await active_machine_rail_service.get(active.id, machine.id)
    lines = [
        f"{machine.name} / смена №{active.shift_number}",
    ]

    if active_rail:
        lines.extend(
            [
                "",
                f"В работе: {active_rail.machine_rail.rail.name}",
                f"Поставил: {active_rail.created_by.full_name}",
            ]
        )
    else:
        lines.extend(["", "В работе: рейка не поставлена."])

    return "\n".join(lines)


def close_shift_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Закрыть смену",
                    callback_data="close_shift_confirm",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="nav:main",
                ),
            ]
        ]
    )


def shift_people_keyboard(
    active_work_sessions,
    mechanics: list[tuple[object, object]],
) -> InlineKeyboardMarkup:
    rows = []

    for work in active_work_sessions:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⏹ {work.machine.name}: {work.user.full_name}",
                    callback_data=f"finish_operator:{work.id}",
                )
            ]
        )

    for mechanic, mechanic_user in mechanics:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"➖ {mechanic_user.full_name}",
                    callback_data=f"finish_mechanic:{mechanic.user_id}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ В меню",
                callback_data="nav:main",
            )
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
        catalog_rail_name(
            data["rail_class"],
            shape,
            data["name"],
            data["length"],
        )
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


async def show_my_machines(
    message: Message,
    user,
    active,
) -> None:
    assignments = await shift_machine_service.get_for_user(
        active.id,
        user.id,
    )
    machines_text = (
        "\n".join(f"- {assignment.machine.name}" for assignment in assignments)
        if assignments
        else "Пока нет закрепленных станков."
    )

    await message.answer(
        f"Мои станки / смена №{active.shift_number}\n\n"
        f"{machines_text}",
        reply_markup=my_machines_keyboard(assignments),
    )


async def show_take_machines(
    message: Message,
    user,
    active,
) -> None:
    machines = await machine_service.get_all()
    assignments = await shift_machine_service.get_by_shift(active.id)

    await message.answer(
        "Выберите станки, за которые отвечаете.\n\n"
        "➕ свободный станок\n"
        "✅ ваш станок, нажмите чтобы убрать\n"
        "👤 закреплен за другим наладчиком",
        reply_markup=take_machines_keyboard(machines, assignments, user.id),
    )


async def ensure_machine_owner(
    user,
    active,
    machine_id: int,
) -> bool:
    if user.role == UserRole.ADMIN:
        return True

    assignment = await shift_machine_service.get_machine_assignment(
        active.id,
        machine_id,
    )

    return assignment is not None and assignment.user_id == user.id


def add_summary(target: dict, source: dict) -> None:
    target["packs"] += source["packs"]
    target["pieces"] += source["pieces"]
    target["meters"] += source["meters"]
    target["operator_total"] += source["operator_total"]
    target["mechanic_total"] += source["mechanic_total"]


def empty_report_summary() -> dict:
    return {
        "packs": 0,
        "pieces": 0,
        "meters": Decimal("0"),
        "operator_total": Decimal("0"),
        "mechanic_total": Decimal("0"),
    }


def summary_line(name: str, data: dict) -> str:
    return (
        f"- {name}: {data['packs']} кор. / {data['pieces']} шт / "
        f"{whole_meters(data['meters'])} м / "
        f"принёс наладчикам {data['mechanic_total']} ₽"
    )


async def shift_close_data(active) -> dict:
    assignments = await shift_machine_service.get_by_shift(active.id)
    active_work_sessions = await work_session_service.get_active_by_shift(
        active.id
    )
    report = await production_service.shift_report(active.id)
    mechanics = await shift_mechanic_service.get_by_shift(active.id)
    active_rails = await active_machine_rail_service.get_by_shift(active.id)

    assignment_by_machine_id = {
        assignment.machine_id: assignment
        for assignment in assignments
    }
    assigned_user_ids = {
        assignment.user_id
        for assignment in assignments
    }
    used_machine_ids = set(report["production_machine_ids"])
    used_machine_ids.update(
        work_session.machine_id
        for work_session in active_work_sessions
    )
    used_machine_ids.update(
        active_rail.machine_id
        for active_rail in active_rails
    )

    unassigned_machine_ids = [
        machine_id
        for machine_id in sorted(used_machine_ids)
        if machine_id not in assignment_by_machine_id
    ]
    unassigned_machines = []

    for machine_id in unassigned_machine_ids:
        machine = await machine_service.get(machine_id)

        if machine:
            unassigned_machines.append(machine)

    mechanics_without_machines = []

    for mechanic in mechanics:
        if mechanic.user_id in assigned_user_ids:
            continue

        mechanic_user = await user_service.get(mechanic.user_id)

        if mechanic_user:
            mechanics_without_machines.append(mechanic_user)

    assigned_without_production = [
        assignment
        for assignment in assignments
        if assignment.machine_id not in report["production_machine_ids"]
    ]

    blockers = []

    if unassigned_machines:
        blockers.append(
            "Станки с работой/продукцией без наладчика:\n"
            + "\n".join(f"- {machine.name}" for machine in unassigned_machines)
        )

    if mechanics_without_machines:
        blockers.append(
            "Наладчики без закреплённых станков:\n"
            + "\n".join(
                f"- {mechanic.full_name}"
                for mechanic in mechanics_without_machines
            )
        )

    warnings = []

    if active_work_sessions:
        warnings.append(
            "Активные операторы будут завершены автоматически:\n"
            + "\n".join(
                f"- {work.machine.name}: {work.user.full_name}"
                for work in active_work_sessions
            )
        )

    if assigned_without_production:
        warnings.append(
            "Закреплены, но без продукции:\n"
            + "\n".join(
                f"- {assignment.machine.name}: {assignment.user.full_name}"
                for assignment in assigned_without_production
            )
        )

    if report["entries_count"] == 0:
        warnings.append("В смене нет записанной продукции.")

    if active_rails:
        warnings.append(
            "Есть рейки в работе без внесённого факта:\n"
            + "\n".join(
                f"- {item.machine.name}: {item.machine_rail.rail.name}"
                for item in active_rails
            )
        )

    return {
        "assignments": assignments,
        "active_work_sessions": active_work_sessions,
        "report": report,
        "assignment_by_machine_id": assignment_by_machine_id,
        "active_rails": active_rails,
        "blockers": blockers,
        "warnings": warnings,
    }


def shift_report_text(active, close_data: dict) -> str:
    report = close_data["report"]
    assignment_by_machine_id = close_data["assignment_by_machine_id"]
    assignments = close_data["assignments"]

    lines = [
        f"Отчёт по смене №{active.shift_number}",
        "",
        "Итого:",
        f"Записей: {report['entries_count']}",
        f"Коробок: {report['packs']}",
        f"Штук: {report['pieces']}",
        f"Пог. метров: {whole_meters(report['meters'])}",
        f"Операторам: {report['operator_total']} ₽",
        f"Наладчикам всего: {report['mechanic_total']} ₽",
    ]

    if report["types"]:
        lines.extend(["", "По типам:"])
        lines.extend(
            summary_line(rail_type, data)
            for rail_type, data in sorted(report["types"].items())
        )

    mechanic_groups = {}

    for assignment in assignments:
        group = mechanic_groups.setdefault(
            assignment.user_id,
            {
                "user_name": assignment.user.full_name,
                "machines": [],
                "summary": empty_report_summary(),
                "types": {},
            },
        )
        machine_summary = report["machines"].get(assignment.machine_id)
        group["machines"].append(assignment.machine.name)

        if not machine_summary:
            continue

        add_summary(group["summary"], machine_summary)

        for rail_type, type_summary in machine_summary["types"].items():
            target = group["types"].setdefault(
                rail_type,
                empty_report_summary(),
            )
            add_summary(target, type_summary)

    if mechanic_groups:
        lines.extend(["", "По наладчикам (сколько принесли их станки):"])

        for group in sorted(
            mechanic_groups.values(),
            key=lambda item: item["user_name"],
        ):
            machines = ", ".join(group["machines"])
            lines.append(f"{group['user_name']} ({machines})")
            lines.append(summary_line("Итого", group["summary"]))

            if group["types"]:
                for rail_type, type_summary in sorted(group["types"].items()):
                    lines.append(f"  {summary_line(rail_type, type_summary)}")

    if report["machines"]:
        lines.extend(["", "По станкам:"])

        for machine_id, machine_summary in sorted(
            report["machines"].items(),
            key=lambda item: item[1]["machine_name"],
        ):
            assignment = assignment_by_machine_id.get(machine_id)
            mechanic_name = (
                assignment.user.full_name
                if assignment
                else "не закреплён"
            )
            lines.append(
                f"{machine_summary['machine_name']} / {mechanic_name}"
            )
            lines.append(summary_line("Итого", machine_summary))

            for rail_type, type_summary in sorted(
                machine_summary["types"].items()
            ):
                lines.append(f"  {summary_line(rail_type, type_summary)}")

    return "\n".join(lines)


async def send_long_message(message: Message, text: str) -> None:
    limit = 3900
    current = []
    current_length = 0

    for line in text.splitlines():
        next_length = current_length + len(line) + 1

        if current and next_length > limit:
            await message.answer("\n".join(current))
            current = []
            current_length = 0

        current.append(line)
        current_length += len(line) + 1

    if current:
        await message.answer("\n".join(current))


async def show_shift_people(message: Message, active) -> None:
    active_work_sessions = await work_session_service.get_active_by_shift(
        active.id
    )
    shift_mechanics = await shift_mechanic_service.get_by_shift(active.id)
    mechanics = []

    for mechanic in shift_mechanics:
        mechanic_user = await user_service.get(mechanic.user_id)

        if mechanic_user:
            mechanics.append((mechanic, mechanic_user))

    operator_lines = (
        [
            f"- {work.machine.name}: {work.user.full_name}"
            for work in active_work_sessions
        ]
        or ["- нет активных операторов"]
    )
    mechanic_lines = (
        [
            f"- {mechanic_user.full_name}: "
            f"{mechanic_status_text(mechanic.mechanic_type)}"
            for mechanic, mechanic_user in mechanics
        ]
        or ["- нет отмеченных наладчиков"]
    )

    await message.answer(
        f"Люди смены №{active.shift_number}\n\n"
        "Операторы на станках:\n"
        f"{chr(10).join(operator_lines)}\n\n"
        "Наладчики:\n"
        f"{chr(10).join(mechanic_lines)}\n\n"
        "Нажмите на человека, чтобы закрыть/убрать его из смены.",
        reply_markup=shift_people_keyboard(active_work_sessions, mechanics),
    )


@router.message(F.text == "🛠 Мои станки")
async def my_machines_message(
    message: Message,
):
    user = await user_service.get_by_telegram_id(message.from_user.id)
    user = await ensure_admin_role(user)

    if user is None:
        await message.answer("Сначала зарегистрируйтесь.")
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await message.answer("Этот раздел доступен наладчику или админу/мастеру.")
        return

    active = await shift_service.get_active_shift()

    if active is None:
        await message.answer("Сначала откройте смену.")
        return

    await show_my_machines(message, user, active)


@router.message(F.text == "👥 Люди смены")
async def shift_people_message(
    message: Message,
):
    user = await user_service.get_by_telegram_id(message.from_user.id)
    user = await ensure_admin_role(user)

    if user is None:
        await message.answer("Сначала зарегистрируйтесь.")
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await message.answer("Раздел доступен наладчику или админу/мастеру.")
        return

    active = await shift_service.get_active_shift()

    if active is None:
        await message.answer("Открытой смены нет.")
        return

    await show_shift_people(message, active)


@router.message(F.text == "✅ Закрыть смену")
async def close_shift_start(
    message: Message,
):
    user = await user_service.get_by_telegram_id(message.from_user.id)
    user = await ensure_admin_role(user)

    if user is None:
        await message.answer("Сначала зарегистрируйтесь.")
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await message.answer("Смену закрывает наладчик или админ/мастер.")
        return

    active = await shift_service.get_active_shift()

    if active is None:
        await message.answer("Открытой смены нет.")
        return

    close_data = await shift_close_data(active)

    if close_data["blockers"]:
        await message.answer(
            "Нельзя закрыть смену.\n\n"
            + "\n\n".join(close_data["blockers"])
            + "\n\nИсправьте закрепление станков и попробуйте снова."
        )
        return

    if close_data["warnings"]:
        await message.answer(
            "Проверка перед закрытием:\n\n"
            + "\n\n".join(close_data["warnings"])
        )
    else:
        await message.answer("Проверка перед закрытием пройдена.")

    await send_long_message(message, shift_report_text(active, close_data))
    await message.answer(
        "Закрыть смену?",
        reply_markup=close_shift_keyboard(),
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
    rails = await production_service.get_enabled_rails()

    if not rails:
        await message.answer(
            "В справочнике пока нет активных реек со ставками.\n\n"
            "Откройте «📚 Справочник реек» и добавьте рейку."
        )
        return

    await state.update_data(prod_filters={}, prod_history=[])
    await send_grouped_rails_step(
        message,
        state,
        mode="prod",
        rails=rails,
    )


@router.message(F.text == "🧮 Тестовый просчет")
async def test_calculation_start(
    message: Message,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(message.from_user.id)
    user = await ensure_admin_role(user)

    if user is None:
        await message.answer("Сначала зарегистрируйтесь.")
        return

    rails = await production_service.get_enabled_rails()

    if not rails:
        await message.answer("В справочнике пока нет активных реек со ставками.")
        return

    await state.clear()
    await state.update_data(test_filters={}, test_history=[])
    await send_grouped_rails_step(
        message,
        state,
        mode="test",
        rails=rails,
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
        "Здесь добавляются новые рейки и редактируются ставки по станкам.",
        reply_markup=admin_keyboard,
    )

    if rails:
        await state.update_data(cat_filters={}, cat_history=[])
        await send_grouped_rails_step(
            message,
            state,
            mode="cat",
            rails=rails,
        )
    else:
        await message.answer("Пока нет заведённых реек.")


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
        "Если добавляете эконом маму и папу с одинаковыми ценами, "
        "нажмите «Мама + Папа».\n"
        "Для GL15 с одинаковыми ценами нажмите «Все виды».\n\n"
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

    if selected == "Все виды" and "L" in available_shapes:
        rail_shapes = available_shapes
    elif selected == "Мама + Папа" and "Напр" in available_shapes:
        rail_shapes = ["Мама", "Папа"]
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

    if rail_shapes != ["Напр"]:
        for rail_shape in rail_shapes:
            target_name = catalog_rail_name(
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
    if rail_shapes == ["Напр"]:
        await message.answer(
            "Выберите длину направляющей:",
            reply_markup=econom_guide_length_keyboard,
        )
        return

    await message.answer(
        "Введите длину одной штуки в метрах.\n\n"
        "Например: 0.6",
        reply_markup=admin_keyboard,
    )


@router.message(AdminRailState.length)
async def admin_rail_length(
    message: Message,
    state: FSMContext,
):
    if message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    data = await state.get_data()
    text = (message.text or "").strip()

    if (
        data.get("rail_shapes") == ["Напр"]
        and text not in ECONOM_GUIDE_LENGTHS
    ):
        await message.answer(
            "Выберите длину направляющей кнопкой.",
            reply_markup=econom_guide_length_keyboard,
        )
        return

    length = parse_decimal(text)

    if length is None or length <= 0:
        await message.answer("Введите длину числом, например 0.6")
        return

    if data.get("rail_shapes") == ["Напр"]:
        target_name = catalog_rail_name(
            data["rail_class"],
            "Напр",
            data["name"],
            text,
        )
        existing_rail = await rail_service.get_by_name(target_name)

        if existing_rail:
            await message.answer(
                "Такая направляющая уже есть в справочнике:\n"
                f"- {existing_rail.name}\n\n"
                "Выберите другую длину или введите другой размер/модель.",
                reply_markup=econom_guide_length_keyboard,
            )
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

    data = await state.get_data()

    if data.get("rail_shapes") == ["Напр"]:
        source_rail = None

        for source_shape in ("Мама", "Папа"):
            source_rail = await rail_service.get_by_name(
                rail_name(data["rail_class"], source_shape, data["name"])
            )

            if source_rail:
                break

        if source_rail:
            rail = await rail_service.create_with_rates_copied_from_rail(
                name=catalog_rail_name(
                    data["rail_class"],
                    "Напр",
                    data["name"],
                    data["length"],
                ),
                length=Decimal(data["length"]),
                pieces_per_pack=pieces_per_pack,
                source_rail_id=source_rail.id,
            )

            await state.clear()

            if rail is None:
                await message.answer(
                    "Не получилось скопировать ставки. "
                    "Попробуйте добавить направляющую вручную.",
                    reply_markup=admin_keyboard,
                )
                return

            await message.answer(
                "✅ Направляющая сохранена со ставками от мамы/папы.\n\n"
                f"Источник ставок: {source_rail.name}\n"
                f"Создано: {rail.name}\n"
                f"Длина: {rail.length} м\n"
                f"Штук в коробке: {rail.pieces_per_pack}",
                reply_markup=admin_keyboard,
            )
            return

        await state.clear()
        await message.answer(
            "Для направляющей цены вручную не вводятся.\n\n"
            "Сначала добавьте эконом «Мама» или «Папа» с таким же размером, "
            "а потом добавьте направляющую — ставки скопируются автоматически.",
            reply_markup=admin_keyboard,
        )
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


@router.callback_query(F.data.startswith("prodsel:"))
async def select_production_group(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer(
            "Продукцию записывает наладчик или админ/мастер."
        )
        await callback.answer()
        return

    data = await state.get_data()
    action = callback.data.split(":", maxsplit=1)[1]

    if action == "reset":
        await state.update_data(prod_filters={}, prod_history=[])
        rails = await production_service.get_enabled_rails()
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="prod",
            rails=rails,
        )
        await callback.answer()
        return

    if action == "back":
        history = data.get("prod_history", [])

        if not history:
            await callback.answer("Это первый шаг.")
            return

        filters = history[-1]
        await state.update_data(
            prod_filters=filters,
            prod_history=history[:-1],
        )
        rails = await production_service.get_enabled_rails()
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="prod",
            rails=rails,
        )
        await callback.answer()
        return

    _, field, index_raw = callback.data.split(":")
    values = data.get("prod_values", [])
    index = int(index_raw)

    if index >= len(values):
        await callback.answer("Выбор устарел. Начните заново.")
        return

    filters = dict(data.get("prod_filters", {}))
    history = data.get("prod_history", [])
    history.append(filters.copy())
    filters[field] = values[index]
    await state.update_data(prod_filters=filters, prod_history=history)
    rails = await production_service.get_enabled_rails()
    await send_grouped_rails_step(
        callback.message,
        state,
        mode="prod",
        rails=rails,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("testsel:"))
async def select_test_group(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None:
        await callback.message.answer("Сначала зарегистрируйтесь.")
        await callback.answer()
        return

    data = await state.get_data()
    action = callback.data.split(":", maxsplit=1)[1]

    if action == "reset":
        await state.update_data(test_filters={}, test_history=[])
        rails = await production_service.get_enabled_rails()
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="test",
            rails=rails,
        )
        await callback.answer()
        return

    if action == "back":
        history = data.get("test_history", [])

        if not history:
            await callback.answer("Это первый шаг.")
            return

        filters = history[-1]
        await state.update_data(
            test_filters=filters,
            test_history=history[:-1],
        )
        rails = await production_service.get_enabled_rails()
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="test",
            rails=rails,
        )
        await callback.answer()
        return

    _, field, index_raw = callback.data.split(":")
    values = data.get("test_values", [])
    index = int(index_raw)

    if index >= len(values):
        await callback.answer("Выбор устарел. Начните заново.")
        return

    filters = dict(data.get("test_filters", {}))
    history = data.get("test_history", [])
    history.append(filters.copy())
    filters[field] = values[index]
    await state.update_data(test_filters=filters, test_history=history)
    rails = await production_service.get_enabled_rails()
    await send_grouped_rails_step(
        callback.message,
        state,
        mode="test",
        rails=rails,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catsel:"))
async def select_catalog_group(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role != UserRole.ADMIN:
        await callback.message.answer("Справочник доступен админу/мастеру.")
        await callback.answer()
        return

    data = await state.get_data()
    action = callback.data.split(":", maxsplit=1)[1]

    if action == "reset":
        await state.update_data(cat_filters={}, cat_history=[])
        rails = await rail_service.get_all()
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="cat",
            rails=rails,
        )
        await callback.answer()
        return

    if action == "back":
        history = data.get("cat_history", [])

        if not history:
            await callback.answer("Это первый шаг.")
            return

        filters = history[-1]
        await state.update_data(
            cat_filters=filters,
            cat_history=history[:-1],
        )
        rails = await rail_service.get_all()
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="cat",
            rails=rails,
        )
        await callback.answer()
        return

    _, field, index_raw = callback.data.split(":")
    values = data.get("cat_values", [])
    index = int(index_raw)

    if index >= len(values):
        await callback.answer("Выбор устарел. Начните заново.")
        return

    filters = dict(data.get("cat_filters", {}))
    history = data.get("cat_history", [])
    history.append(filters.copy())
    filters[field] = values[index]
    await state.update_data(cat_filters=filters, cat_history=history)
    rails = await rail_service.get_all()
    await send_grouped_rails_step(
        callback.message,
        state,
        mode="cat",
        rails=rails,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mprodsel:"))
async def select_machine_production_group(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer(
            "Продукцию записывает наладчик или админ/мастер."
        )
        await callback.answer()
        return

    data = await state.get_data()
    machine_id = data.get("mprod_machine_id")

    if machine_id is None:
        await callback.message.answer("Станок не выбран. Откройте «Мои станки».")
        await callback.answer()
        return

    action = callback.data.split(":", maxsplit=1)[1]

    if action == "reset":
        await state.update_data(mprod_filters={}, mprod_history=[])
        machine_rails = await production_service.get_enabled_rails_for_machine(
            machine_id
        )
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="mprod",
            rails=[machine_rail.rail for machine_rail in machine_rails],
        )
        await callback.answer()
        return

    if action == "back":
        history = data.get("mprod_history", [])

        if not history:
            await callback.answer("Это первый шаг.")
            return

        filters = history[-1]
        await state.update_data(
            mprod_filters=filters,
            mprod_history=history[:-1],
        )
        machine_rails = await production_service.get_enabled_rails_for_machine(
            machine_id
        )
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="mprod",
            rails=[machine_rail.rail for machine_rail in machine_rails],
        )
        await callback.answer()
        return

    _, field, index_raw = callback.data.split(":")
    values = data.get("mprod_values", [])
    index = int(index_raw)

    if index >= len(values):
        await callback.answer("Выбор устарел. Начните заново.")
        return

    filters = dict(data.get("mprod_filters", {}))
    history = data.get("mprod_history", [])
    history.append(filters.copy())
    filters[field] = values[index]
    await state.update_data(mprod_filters=filters, mprod_history=history)
    machine_rails = await production_service.get_enabled_rails_for_machine(
        machine_id
    )
    await send_grouped_rails_step(
        callback.message,
        state,
        mode="mprod",
        rails=[machine_rail.rail for machine_rail in machine_rails],
    )
    await callback.answer()


@router.callback_query(F.data.startswith("nav:"))
async def inline_navigation(
    callback: CallbackQuery,
    state: FSMContext,
):
    action = callback.data.split(":", maxsplit=1)[1]

    if action == "main":
        await state.clear()
        await callback.message.answer(
            "Главное меню.",
            reply_markup=main_keyboard,
        )
        await callback.answer()
        return

    if action == "production_start":
        user = await user_service.get_by_telegram_id(callback.from_user.id)
        user = await ensure_admin_role(user)

        if user is None or user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
            await callback.message.answer(
                "Продукцию записывает наладчик или админ/мастер."
            )
            await callback.answer()
            return

        await state.clear()
        rails = await production_service.get_enabled_rails()

        if not rails:
            await callback.message.answer(
                "В справочнике пока нет активных реек со ставками.\n\n"
                "Откройте «📚 Справочник реек» и добавьте рейку."
            )
            await callback.answer()
            return

        await state.update_data(prod_filters={}, prod_history=[])
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="prod",
            rails=rails,
        )
        await callback.answer()
        return

    if action == "prod_current":
        user = await user_service.get_by_telegram_id(callback.from_user.id)
        user = await ensure_admin_role(user)

        if user is None or user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
            await callback.message.answer(
                "Продукцию записывает наладчик или админ/мастер."
            )
            await callback.answer()
            return

        rails = await production_service.get_enabled_rails()
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="prod",
            rails=rails,
        )
        await callback.answer()
        return

    if action == "admin_start":
        user = await user_service.get_by_telegram_id(callback.from_user.id)
        user = await ensure_admin_role(user)

        if user is None or user.role != UserRole.ADMIN:
            await callback.message.answer("Справочник доступен админу/мастеру.")
            await callback.answer()
            return

        rails = await rail_service.get_all()
        await state.update_data(cat_filters={}, cat_history=[])
        await send_grouped_rails_step(
            callback.message,
            state,
            mode="cat",
            rails=rails,
        )
        await callback.answer()
        return

    await callback.answer("Неизвестное действие.")


@router.callback_query(F.data == "close_shift_confirm")
async def close_shift_confirm(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer(
            "Смену закрывает наладчик или админ/мастер."
        )
        await callback.answer()
        return

    active = await shift_service.get_active_shift()

    if active is None:
        await callback.message.answer("Открытой смены нет.")
        await callback.answer()
        return

    close_data = await shift_close_data(active)

    if close_data["blockers"]:
        await callback.message.answer(
            "Смена не закрыта.\n\n"
            + "\n\n".join(close_data["blockers"])
        )
        await callback.answer()
        return

    report_text = shift_report_text(active, close_data)
    finished_sessions = await work_session_service.finish_by_shift(active.id)
    closed = await shift_service.finish_shift()

    if not closed:
        await callback.message.answer("Не получилось закрыть смену.")
        await callback.answer()
        return

    await callback.message.answer(
        f"✅ Смена №{active.shift_number} закрыта.\n"
        f"Завершено активных операторов: {finished_sessions}",
        reply_markup=main_keyboard,
    )
    await send_long_message(callback.message, report_text)
    await callback.answer()


@router.callback_query(F.data.startswith("finish_operator:"))
async def finish_operator_from_shift(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer("Раздел доступен наладчику.")
        await callback.answer()
        return

    work_session_id = int(callback.data.split(":", maxsplit=1)[1])
    work = await work_session_service.finish_by_id(work_session_id, active.id)

    if work is None:
        await callback.message.answer("Оператор уже закрыт или смена не найдена.")
        await callback.answer()
        return

    await callback.message.answer(
        f"✅ Оператор закрыт.\n\n"
        f"{work.machine.name}: {work.user.full_name}"
    )
    await show_shift_people(callback.message, active)
    await callback.answer()


@router.callback_query(F.data.startswith("finish_mechanic:"))
async def finish_mechanic_from_shift(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer("Раздел доступен наладчику.")
        await callback.answer()
        return

    mechanic_user_id = int(callback.data.split(":", maxsplit=1)[1])
    mechanic_user = await user_service.get(mechanic_user_id)
    removed = await shift_mechanic_service.remove(
        active.id,
        mechanic_user_id,
    )

    if not removed:
        await callback.message.answer("Наладчик уже убран из смены.")
        await callback.answer()
        return

    name = mechanic_user.full_name if mechanic_user else "Наладчик"
    await callback.message.answer(f"✅ {name} убран из текущей смены.")
    await show_shift_people(callback.message, active)
    await callback.answer()


@router.callback_query(F.data == "my_machines")
async def my_machines_callback(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer("Этот раздел доступен наладчику.")
        await callback.answer()
        return

    await show_my_machines(callback.message, user, active)
    await callback.answer()


@router.callback_query(F.data == "my_machine_take")
async def take_machines_callback(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer("Этот раздел доступен наладчику.")
        await callback.answer()
        return

    await show_take_machines(callback.message, user, active)
    await callback.answer()


@router.callback_query(F.data.startswith("assign_machine:"))
async def assign_machine_to_mechanic(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer("Этот раздел доступен наладчику.")
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])
    ok, text = await shift_machine_service.assign(
        active.id,
        user.id,
        machine_id,
    )
    await callback.message.answer(("✅ " if ok else "⚠️ ") + text)
    await show_take_machines(callback.message, user, active)
    await callback.answer()


@router.callback_query(F.data.startswith("unassign_machine:"))
async def unassign_machine_from_mechanic(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])
    removed = await shift_machine_service.unassign(
        active.id,
        user.id,
        machine_id,
    )
    await callback.message.answer(
        "✅ Станок убран из вашего списка."
        if removed
        else "Станок не был в вашем списке."
    )
    await show_my_machines(callback.message, user, active)
    await callback.answer()


@router.callback_query(F.data.startswith("taken_machine:"))
async def show_taken_machine_owner(
    callback: CallbackQuery,
):
    active = await shift_service.get_active_shift()

    if active is None:
        await callback.answer("Смена не найдена.")
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])
    assignment = await shift_machine_service.get_machine_assignment(
        active.id,
        machine_id,
    )

    if assignment is None:
        await callback.answer("Станок свободен.")
        return

    await callback.answer(
        f"Закреплен за {assignment.user.full_name}.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("my_machine:"))
async def my_machine_panel(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])

    if not await ensure_machine_owner(user, active, machine_id):
        await callback.message.answer(
            "Этот станок не закреплен за вами в текущей смене."
        )
        await callback.answer()
        return

    machine = await machine_service.get(machine_id)

    if machine is None:
        await callback.message.answer("Станок не найден.")
        await callback.answer()
        return

    await callback.message.answer(
        await my_machine_panel_text(machine, active),
        reply_markup=my_machine_panel_keyboard(machine.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("my_machine_summary:"))
async def my_machine_summary(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])

    if not await ensure_machine_owner(user, active, machine_id):
        await callback.message.answer(
            "Этот станок не закреплен за вами в текущей смене."
        )
        await callback.answer()
        return

    machine = await machine_service.get(machine_id)
    summary = await production_service.machine_shift_summary(
        active.id,
        machine_id,
    )

    if machine is None:
        await callback.message.answer("Станок не найден.")
        await callback.answer()
        return

    if summary["entries_count"] == 0:
        await callback.message.answer(
            f"{machine.name} / смена №{active.shift_number}\n\n"
            "Продукция пока не внесена.",
            reply_markup=my_machine_panel_keyboard(machine.id),
        )
        await callback.answer()
        return

    type_lines = [
        f"- {rail_type}: {data['packs']} кор. / {data['pieces']} шт / "
        f"{whole_meters(data['meters'])} м"
        for rail_type, data in sorted(summary["types"].items())
    ]
    await callback.message.answer(
        f"{machine.name} / смена №{active.shift_number}\n\n"
        f"Записей: {summary['entries_count']}\n"
        f"Коробок: {summary['packs']}\n"
        f"Штук: {summary['pieces']}\n"
        f"Пог. метров: {whole_meters(summary['meters'])}\n"
        f"Операторам: {summary['operator_total']} ₽\n"
        f"Наладчикам: {summary['mechanic_total']} ₽\n\n"
        "По типам:\n"
        f"{chr(10).join(type_lines)}",
        reply_markup=my_machine_panel_keyboard(machine.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("myprod_start:"))
async def my_machine_product_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])

    if not await ensure_machine_owner(user, active, machine_id):
        await callback.message.answer(
            "Этот станок не закреплен за вами в текущей смене."
        )
        await callback.answer()
        return

    frequent_rails = await production_service.get_frequent_rails_for_machine(
        machine_id
    )

    if frequent_rails:
        await state.clear()
        await state.update_data(mprod_machine_id=machine_id)
        await callback.message.answer(
            "Частые рейки на этом станке:",
            reply_markup=frequent_rails_keyboard(
                machine_id,
                frequent_rails,
                choose_callback="mprod_confirm_rail",
                catalog_callback="mprod_catalog",
                back_callback=f"my_machine:{machine_id}",
            ),
        )
        await callback.answer()
        return

    machine_rails = await production_service.get_enabled_rails_for_machine(
        machine_id
    )

    if not machine_rails:
        await callback.message.answer(
            "Для этого станка пока нет активных реек/ставок."
        )
        await callback.answer()
        return

    await state.clear()
    await state.update_data(
        mprod_machine_id=machine_id,
        mprod_filters={},
        mprod_history=[],
    )
    await send_grouped_rails_step(
        callback.message,
        state,
        mode="mprod",
        rails=[machine_rail.rail for machine_rail in machine_rails],
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
    frequent_rails = await production_service.get_frequent_rails_for_machine(
        machine_id
    )

    if frequent_rails:
        await callback.message.answer(
            "Частые рейки на этом станке:",
            reply_markup=frequent_rails_keyboard(
                machine_id,
                frequent_rails,
                choose_callback="prod_freq_rail",
                catalog_callback="prod_catalog",
                back_callback="nav:production_start",
            ),
        )
        await callback.answer()
        return

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


@router.callback_query(F.data.startswith("prod_catalog:"))
async def production_machine_catalog(
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


@router.callback_query(F.data.startswith("prod_freq_rail:"))
async def select_frequent_production_rail(
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

    await set_active_machine_rail(
        callback,
        state,
        machine_id=int(machine_id_raw),
        machine_rail_id=int(machine_rail_id_raw),
        require_owner=False,
    )


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


@router.callback_query(F.data.startswith("prod_confirm_rail:"))
async def confirm_production_rail(
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


@router.callback_query(F.data.startswith("test_rail_first:"))
@router.callback_query(F.data.startswith("test_confirm_rail:"))
async def select_test_rail(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None:
        await callback.message.answer("Сначала зарегистрируйтесь.")
        await callback.answer()
        return

    rail_id = int(callback.data.split(":", maxsplit=1)[1])
    keyboard_markup = await production_machines_for_rail_keyboard(
        rail_id,
        callback_prefix="test_machine_for_rail",
        back_callback="testsel:back",
        reset_callback="testsel:reset",
    )

    if not keyboard_markup.inline_keyboard:
        await callback.message.answer(
            "Для этой рейки пока нет активных ставок по станкам."
        )
        await callback.answer()
        return

    await callback.message.answer(
        "Выберите станок для тестового просчёта:",
        reply_markup=keyboard_markup,
    )
    await callback.answer()


async def set_active_machine_rail(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    machine_id: int,
    machine_rail_id: int,
    require_owner: bool,
) -> None:
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer(
            "Рейку ставит в работу наладчик или админ/мастер."
        )
        await callback.answer()
        return

    if require_owner and not await ensure_machine_owner(user, active, machine_id):
        await callback.message.answer(
            "Этот станок не закреплен за вами в текущей смене."
        )
        await callback.answer()
        return

    machine_rail = await production_service.get_enabled_machine_rail_by_id(
        machine_rail_id,
    )

    if machine_rail is None or machine_rail.machine_id != machine_id:
        await callback.message.answer(
            "Для этой рейки нет активной ставки на выбранном станке."
        )
        await callback.answer()
        return

    await active_machine_rail_service.set_active(active, machine_rail, user)
    await state.clear()
    await callback.message.answer(
        "✅ Рейка поставлена в работу.\n\n"
        f"Станок: {machine_rail.machine.name}\n"
        f"Рейка: {machine_rail.rail.name}\n\n"
        "Деньги и продукция пока не считаются. "
        "Когда рейка будет сделана, нажмите «✅ Завершить рейку».",
        reply_markup=my_machine_panel_keyboard(machine_rail.machine.id),
    )
    await callback.answer()


async def start_machine_product_work(
    callback: CallbackQuery,
    state: FSMContext,
    rail_id: int,
) -> None:
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()
    data = await state.get_data()
    machine_id = data.get("mprod_machine_id")

    if user is None or active is None or machine_id is None:
        await callback.message.answer("Смена или станок не найдены.")
        await callback.answer()
        return

    if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
        await callback.message.answer(
            "Продукцию записывает наладчик или админ/мастер."
        )
        await callback.answer()
        return

    if not await ensure_machine_owner(user, active, machine_id):
        await callback.message.answer(
            "Этот станок не закреплен за вами в текущей смене."
        )
        await callback.answer()
        return

    machine_rail = await production_service.get_enabled_machine_rail(
        machine_id,
        rail_id,
    )

    if machine_rail is None:
        await callback.message.answer(
            "Для этой рейки нет активной ставки на выбранном станке."
        )
        await callback.answer()
        return

    await set_active_machine_rail(
        callback,
        state,
        machine_id=machine_id,
        machine_rail_id=machine_rail.id,
        require_owner=True,
    )


@router.callback_query(F.data.startswith("mprod_confirm_rail:"))
async def confirm_machine_production_rail(
    callback: CallbackQuery,
    state: FSMContext,
):
    rail_id = int(callback.data.split(":", maxsplit=1)[1])
    await start_machine_product_work(callback, state, rail_id)


@router.callback_query(F.data.startswith("mprod_rail:"))
async def select_machine_production_rail(
    callback: CallbackQuery,
    state: FSMContext,
):
    rail_id = int(callback.data.split(":", maxsplit=1)[1])
    await start_machine_product_work(callback, state, rail_id)


@router.callback_query(F.data.startswith("mprod_catalog:"))
async def machine_production_catalog(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])

    if not await ensure_machine_owner(user, active, machine_id):
        await callback.message.answer(
            "Этот станок не закреплен за вами в текущей смене."
        )
        await callback.answer()
        return

    machine_rails = await production_service.get_enabled_rails_for_machine(
        machine_id
    )

    if not machine_rails:
        await callback.message.answer(
            "Для этого станка пока нет активных реек/ставок."
        )
        await callback.answer()
        return

    await state.update_data(
        mprod_machine_id=machine_id,
        mprod_filters={},
        mprod_history=[],
    )
    await send_grouped_rails_step(
        callback.message,
        state,
        mode="mprod",
        rails=[machine_rail.rail for machine_rail in machine_rails],
    )
    await callback.answer()


@router.callback_query(F.data.startswith("finish_active_rail:"))
async def finish_active_rail(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])

    if not await ensure_machine_owner(user, active, machine_id):
        await callback.message.answer(
            "Этот станок не закреплен за вами в текущей смене."
        )
        await callback.answer()
        return

    active_rail = await active_machine_rail_service.get(active.id, machine_id)

    if active_rail is None:
        await callback.message.answer("На этом станке нет рейки в работе.")
        await callback.answer()
        return

    await state.clear()
    await state.update_data(
        entry_mode="active_finish",
        machine_id=machine_id,
        machine_rail_id=active_rail.machine_rail_id,
        mprod_machine_id=machine_id,
    )
    await state.set_state(ProductionState.packs)
    await callback.message.answer(
        f"Завершение рейки.\n\n"
        f"Станок: {active_rail.machine.name}\n"
        f"Рейка: {active_rail.machine_rail.rail.name}\n\n"
        "Введите фактическое количество коробок целым числом:"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("clear_active_rail:"))
async def clear_active_rail(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)
    active = await shift_service.get_active_shift()

    if user is None or active is None:
        await callback.message.answer("Смена не найдена.")
        await callback.answer()
        return

    machine_id = int(callback.data.split(":", maxsplit=1)[1])

    if not await ensure_machine_owner(user, active, machine_id):
        await callback.message.answer(
            "Этот станок не закреплен за вами в текущей смене."
        )
        await callback.answer()
        return

    cleared = await active_machine_rail_service.clear(active.id, machine_id)
    machine = await machine_service.get(machine_id)

    await callback.message.answer(
        (
            "🗑 Рейка убрана без отчёта."
            if cleared
            else "На этом станке нет рейки в работе."
        ),
        reply_markup=(
            my_machine_panel_keyboard(machine.id)
            if machine
            else None
        ),
    )
    await callback.answer()


def rail_rates_text(rates) -> str:
    if not rates:
        return "Ставки по станкам не заведены."

    lines = []

    for rate in rates:
        status = "" if rate.is_enabled else " (выкл.)"
        lines.append(
            f"- {rate.machine.name}: "
            f"{rate.mechanic_price}/{rate.operator_price}{status}"
        )

    return "\n".join(lines)


def rail_edit_keyboard(rail_id: int, machines) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✏️ Длина/фасовка",
                callback_data=f"editparams:{rail_id}",
            ),
            InlineKeyboardButton(
                text="✅ Включить ставки",
                callback_data=f"enablerates:{rail_id}",
            ),
        ]
    ]

    for machine in machines:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {machine.name}",
                    callback_data=f"editrate:{rail_id}:{machine.id}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К списку",
                callback_data="catback",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("catrail:"))
async def show_catalog_rail(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role != UserRole.ADMIN:
        await callback.message.answer("Справочник доступен админу/мастеру.")
        await callback.answer()
        return

    rail_id = int(callback.data.split(":", maxsplit=1)[1])
    rail, rates = await rail_service.get_with_rates(rail_id)
    machines = await machine_service.get_all()

    if rail is None:
        await callback.message.answer("Рейка не найдена.")
        await callback.answer()
        return

    await callback.message.answer(
        "Карточка рейки\n\n"
        f"{rail.name}\n"
        f"Длина: {rail.length} м\n"
        f"Штук в коробке: {rail.pieces_per_pack}\n\n"
        "Ставки: наладчик/оператор\n"
        f"{rail_rates_text(rates)}",
        reply_markup=rail_edit_keyboard(rail.id, machines),
    )
    await callback.answer()


@router.callback_query(F.data == "catback")
async def back_to_catalog_groups(
    callback: CallbackQuery,
    state: FSMContext,
):
    rails = await rail_service.get_all()
    await state.update_data(cat_filters={}, cat_history=[])
    await send_grouped_rails_step(
        callback.message,
        state,
        mode="cat",
        rails=rails,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("editparams:"))
async def start_edit_rail_params(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role != UserRole.ADMIN:
        await callback.message.answer("Справочник доступен админу/мастеру.")
        await callback.answer()
        return

    rail_id = int(callback.data.split(":", maxsplit=1)[1])
    rail = await rail_service.get(rail_id)

    if rail is None:
        await callback.message.answer("Рейка не найдена.")
        await callback.answer()
        return

    await state.update_data(edit_rail_id=rail_id)
    await state.set_state(AdminRailState.edit_rail_params)
    await callback.message.answer(
        f"Рейка: {rail.name}\n\n"
        "Введите длину и фасовку через пробел.\n"
        "Например: 0.6 192",
        reply_markup=admin_keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("enablerates:"))
async def enable_catalog_rail_rates(
    callback: CallbackQuery,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role != UserRole.ADMIN:
        await callback.message.answer("Справочник доступен админу/мастеру.")
        await callback.answer()
        return

    rail_id = int(callback.data.split(":", maxsplit=1)[1])
    enabled_count = await rail_service.enable_machine_rates(rail_id)
    await callback.message.answer(f"Включено ставок: {enabled_count}.")
    await callback.answer()


@router.message(AdminRailState.edit_rail_params)
async def edit_rail_params(
    message: Message,
    state: FSMContext,
):
    if message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    parts = (message.text or "").replace(";", " ").replace(",", ".").split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(
            "Введите длину и фасовку через пробел.\n"
            "Например: 0.6 192"
        )
        return

    length = parse_decimal(parts[0])
    pieces_per_pack = int(parts[1])

    if length is None or length <= 0 or pieces_per_pack <= 0:
        await message.answer("Длина и фасовка должны быть больше нуля.")
        return

    data = await state.get_data()
    rail = await rail_service.update_params(
        rail_id=data["edit_rail_id"],
        length=length,
        pieces_per_pack=pieces_per_pack,
    )
    await state.clear()

    if rail is None:
        await message.answer("Рейка не найдена.", reply_markup=admin_keyboard)
        return

    await message.answer(
        "Параметры рейки обновлены.\n\n"
        f"{rail.name}\n"
        f"Длина: {rail.length} м\n"
        f"Штук в коробке: {rail.pieces_per_pack}",
        reply_markup=admin_keyboard,
    )


@router.callback_query(F.data.startswith("editrate:"))
async def start_edit_rail_rate(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None or user.role != UserRole.ADMIN:
        await callback.message.answer("Справочник доступен админу/мастеру.")
        await callback.answer()
        return

    _, rail_id_raw, machine_id_raw = callback.data.split(":")
    rail_id = int(rail_id_raw)
    machine_id = int(machine_id_raw)
    rail = await rail_service.get(rail_id)
    machine = await machine_service.get(machine_id)

    if rail is None or machine is None:
        await callback.message.answer("Рейка или станок не найдены.")
        await callback.answer()
        return

    await state.update_data(
        edit_rail_id=rail_id,
        edit_machine_id=machine_id,
    )
    await state.set_state(AdminRailState.edit_machine_rate)
    await callback.message.answer(
        f"Рейка: {rail.name}\n"
        f"Станок: {machine.name}\n\n"
        "Введите ставки через пробел: наладчик оператор.\n"
        "Например: 93.25 199.18\n\n"
        "Или нажмите «⏭ Пропустить», чтобы отключить рейку на этом станке.",
        reply_markup=admin_skip_keyboard,
    )
    await callback.answer()


@router.message(AdminRailState.edit_machine_rate)
async def edit_rail_machine_rate(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()
    rail_id = data["edit_rail_id"]
    machine_id = data["edit_machine_id"]

    if message.text == "↩️ Назад":
        await back_to_main(message, state)
        return

    if message.text == "⏭ Пропустить":
        await rail_service.disable_machine_rate(rail_id, machine_id)
        await state.clear()
        await message.answer(
            "Ставка отключена для выбранного станка.",
            reply_markup=admin_keyboard,
        )
        return

    prices = parse_mechanic_operator_rate(message.text or "")

    if prices is None:
        await message.answer(
            "Введите две ставки через пробел: наладчик оператор.\n"
            "Например: 93.25 199.18"
        )
        return

    mechanic_price, operator_price = prices
    await rail_service.set_machine_rate(
        rail_id=rail_id,
        machine_id=machine_id,
        operator_price=operator_price,
        mechanic_price=mechanic_price,
        is_enabled=True,
    )
    await state.clear()
    await message.answer(
        "Ставка обновлена.",
        reply_markup=admin_keyboard,
    )


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

    await set_active_machine_rail(
        callback,
        state,
        machine_id=int(machine_id_raw),
        machine_rail_id=int(machine_rail_id_raw),
        require_owner=False,
    )


@router.callback_query(F.data.startswith("test_machine_for_rail:"))
async def select_test_machine_for_rail(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(callback.from_user.id)
    user = await ensure_admin_role(user)

    if user is None:
        await callback.message.answer("Сначала зарегистрируйтесь.")
        await callback.answer()
        return

    _, machine_id_raw, machine_rail_id_raw = callback.data.split(":")
    machine_rail = await production_service.get_enabled_machine_rail_by_id(
        int(machine_rail_id_raw),
    )

    if machine_rail is None or machine_rail.machine_id != int(machine_id_raw):
        await callback.message.answer(
            "Для этой рейки нет активной ставки на выбранном станке."
        )
        await callback.answer()
        return

    await state.update_data(
        entry_mode="test_calc",
        machine_id=int(machine_id_raw),
        machine_rail_id=int(machine_rail_id_raw),
    )
    await state.set_state(ProductionState.packs)

    await callback.message.answer(
        "Тестовый просчёт.\n\n"
        f"Станок: {machine_rail.machine.name}\n"
        f"Рейка: {machine_rail.rail.name}\n\n"
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

    await set_active_machine_rail(
        callback,
        state,
        machine_id=int(machine_id_raw),
        machine_rail_id=int(machine_rail_id_raw),
        require_owner=False,
    )


@router.message(ProductionState.packs)
async def input_production_packs(
    message: Message,
    state: FSMContext,
):
    user = await user_service.get_by_telegram_id(
        message.from_user.id
    )
    user = await ensure_admin_role(user)
    data = await state.get_data()
    entry_mode = data.get("entry_mode")

    if user is None:
        await message.answer("Сначала зарегистрируйтесь.")
        await state.clear()
        return

    active = None

    if entry_mode != "test_calc":
        active = await shift_service.get_active_shift()

        if user.role not in (UserRole.ADMIN, UserRole.MECHANIC):
            await message.answer("Продукцию добавляет наладчик или админ/мастер.")
            await state.clear()
            return

        if active is None:
            await message.answer("Смена не открыта.")
            await state.clear()
            return

    if message.text == "↩️ Назад":
        machine_id = data.get("mprod_machine_id") or data.get("machine_id")
        await state.clear()

        if machine_id and active is not None:
            machine = await machine_service.get(machine_id)

            if machine:
                await message.answer(
                    await my_machine_panel_text(machine, active),
                    reply_markup=my_machine_panel_keyboard(machine.id),
                )
                return

        await message.answer(
            "Главное меню.",
            reply_markup=main_keyboard,
        )
        return

    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите количество коробок целым числом.")
        return

    packs = int(message.text.strip())

    if packs <= 0:
        await message.answer("Количество коробок должно быть больше нуля.")
        return

    if entry_mode == "test_calc":
        try:
            machine, rail, calculation = await production_service.calculate_entry(
                data["machine_rail_id"],
                packs,
            )
        except ValueError as error:
            await message.answer(str(error))
            await state.clear()
            return

        await state.clear()
        payable_text = (
            f"Расчетных штук: {calculation['payable_pieces']}\n"
            if calculation["payable_pieces"] != calculation["pieces"]
            else ""
        )
        await message.answer(
            "🧮 Тестовый просчёт.\n\n"
            f"Станок: {machine.name}\n"
            f"Рейка: {rail.name}\n"
            f"Коробок: {packs}\n"
            f"Штук: {calculation['pieces']}\n"
            f"{payable_text}"
            f"Пог. метров: {whole_meters(calculation['meters'])}\n"
            f"Оператору: {calculation['operator_total']} ₽\n"
            f"Наладчикам всего: {calculation['mechanic_total']} ₽\n\n"
            "В отчёт смены это не записано.",
            reply_markup=main_keyboard,
        )
        return

    try:
        (
            entry,
            machine,
            rail,
            operator_total,
            mechanic_total,
            payable_pieces,
        ) = (
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

    if entry_mode == "active_finish":
        await active_machine_rail_service.clear(active.id, data["machine_id"])

    started_from_my_machine = data.get("mprod_machine_id") is not None
    await state.clear()
    payable_text = (
        f"Расчетных штук: {payable_pieces}\n"
        if payable_pieces != entry.pieces
        else ""
    )

    await message.answer(
        "✅ Продукция добавлена.\n\n"
        f"Смена №{active.shift_number}\n"
        f"Станок: {machine.name}\n"
        f"Рейка: {rail.name}\n"
        f"Коробок: {entry.packs}\n"
        f"Штук: {entry.pieces}\n"
        f"{payable_text}"
        f"Пог. метров: {whole_meters(Decimal(str(entry.meters)))}\n"
        f"Оператор: {entry.operator_name}\n"
        f"Оператору: {operator_total} ₽\n"
        f"Наладчикам всего: {mechanic_total} ₽",
        reply_markup=(
            my_machine_panel_keyboard(machine.id)
            if started_from_my_machine
            else None
        ),
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
    await show_my_machines(callback.message, user, active)
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
