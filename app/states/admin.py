from aiogram.fsm.state import State, StatesGroup


class AdminRailState(StatesGroup):
    rail_class = State()
    rail_shapes = State()
    name = State()
    length = State()
    pieces_per_pack = State()
    machine_rate = State()
    edit_machine_rate = State()
