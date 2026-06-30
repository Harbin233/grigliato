from datetime import datetime

from app.models.shift import ShiftType


def current_shift_type() -> ShiftType:
    hour = datetime.now().hour

    if 8 <= hour < 20:
        return ShiftType.DAY

    return ShiftType.NIGHT
