from aiogram.fsm.state import State, StatesGroup


class ProductionState(StatesGroup):
    packs = State()
    roll_weight = State()
