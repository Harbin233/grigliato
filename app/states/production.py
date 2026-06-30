from aiogram.fsm.state import State, StatesGroup


class ProductionState(StatesGroup):
    packs = State()
