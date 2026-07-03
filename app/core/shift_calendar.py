from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.shift import ShiftType

BASE_DATE = date(2026, 6, 25)

SHIFT_PATTERN = [
    (4, 3),
    (2, 1),
    (2, 1),
    (3, 4),
    (3, 4),
    (1, 2),
    (1, 2),
    (4, 3),
]

DAY_START = time(8, 0)
NIGHT_START = time(20, 0)

EARLY_START_MINUTES = 60


@dataclass(frozen=True)
class ResolvedShift:
    work_date: date
    shift_type: ShiftType
    shift_number: int


def get_shift_numbers_for_date(work_date: date) -> tuple[int, int]:
    days_passed = (work_date - BASE_DATE).days
    pattern_index = days_passed % len(SHIFT_PATTERN)
    return SHIFT_PATTERN[pattern_index]


def resolve_shift(now: datetime | None = None) -> ResolvedShift:
    timezone = ZoneInfo(settings.TIMEZONE)

    if now is None:
        now = datetime.now(timezone)
    elif now.tzinfo is not None:
        now = now.astimezone(timezone)

    current_date = now.date()
    current_time = now.time()

    night_open_from = (
        datetime.combine(current_date, NIGHT_START)
        - timedelta(minutes=EARLY_START_MINUTES)
    ).time()

    # Ночная смена может открываться с 19:00
    if current_time >= night_open_from:
        work_date = current_date
        _, night_shift = get_shift_numbers_for_date(work_date)

        return ResolvedShift(
            work_date=work_date,
            shift_type=ShiftType.NIGHT,
            shift_number=night_shift,
        )

    # До 08:00 ещё считается предыдущая ночная смена
    if current_time < DAY_START:
        work_date = current_date - timedelta(days=1)
        _, night_shift = get_shift_numbers_for_date(work_date)

        return ResolvedShift(
            work_date=work_date,
            shift_type=ShiftType.NIGHT,
            shift_number=night_shift,
        )

    # С 08:00 начинается дневная смена
    work_date = current_date
    day_shift, _ = get_shift_numbers_for_date(work_date)

    return ResolvedShift(
        work_date=work_date,
        shift_type=ShiftType.DAY,
        shift_number=day_shift,
    )
