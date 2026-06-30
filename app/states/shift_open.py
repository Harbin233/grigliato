from aiogram.fsm.state import State, StatesGroup


class ShiftOpenState(StatesGroup):
    shift_type = State()
    main_mechanic = State()
    assistant_mechanic = State()
