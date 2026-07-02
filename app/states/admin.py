from aiogram.fsm.state import State, StatesGroup


class AdminRailState(StatesGroup):
    name = State()
    length = State()
    pieces_per_pack = State()
    operator_price = State()
    mechanic_price = State()
