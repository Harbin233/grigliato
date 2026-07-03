from datetime import date, datetime

from sqlalchemy import select

from app.core.shift_calendar import resolve_shift
from app.db.session import SessionLocal
from app.models.shift import Shift, ShiftType
from app.models.user import User, UserRole


def shift_matches_resolved(
    shift: Shift,
    resolved,
) -> bool:
    return (
        shift.work_date == resolved.work_date
        and shift.shift_type == resolved.shift_type
        and shift.shift_number == resolved.shift_number
    )


class ShiftService:

    async def get_active_shift(
        self,
    ) -> Shift | None:

        async with SessionLocal() as session:

            result = await session.execute(
                select(Shift).where(
                    Shift.ended_at.is_(None)
                )
            )

            return result.scalar_one_or_none()


    async def start_shift(
        self,
        user: User,
        allow_overtime: bool = False,
    ) -> tuple[bool, str]:

        active = await self.get_active_shift()
        resolved = resolve_shift()

        if active and shift_matches_resolved(active, resolved):
            return (
                True,
                f"Смена №{active.shift_number} уже открыта."
            )

        if user.role == UserRole.OPERATOR:
            return (
                False,
                "Смену открывает наладчик или админ/мастер."
            )

        if (
            user.role == UserRole.MECHANIC
            and user.shift_number != resolved.shift_number
            and not allow_overtime
        ):
            return (
                False,
                f"Сейчас работает смена №{resolved.shift_number}.\n"
                "Если выходите на подработку, нажмите кнопку «🕒 Подработка»."
            )

        async with SessionLocal() as session:
            if active:
                db_active = await session.get(Shift, active.id)
                db_active.ended_at = datetime.now()

            shift = Shift(
                work_date=resolved.work_date,
                shift_number=resolved.shift_number,
                shift_type=resolved.shift_type,
                started_at=datetime.now(),
                started_by_id=user.id,
            )

            session.add(shift)

            await session.commit()

            await session.refresh(
                shift
            )

            return (
                True,
                f"Открыта смена №{shift.shift_number}."
            )


    async def force_start_shift(
        self,
        work_date: date,
        shift_type: ShiftType,
        shift_number: int,
        user: User,
    ) -> Shift:

        active = await self.get_active_shift()

        if active:

            async with SessionLocal() as session:

                db_shift = await session.get(
                    Shift,
                    active.id,
                )

                db_shift.ended_at = datetime.now()

                await session.commit()
            async with SessionLocal() as session:

                shift = Shift(
                    work_date=work_date,
                    shift_number=shift_number,
                    shift_type=shift_type,
                    started_at=datetime.now(),
                    started_by_id=user.id,
                )

                session.add(shift)

                await session.commit()
                await session.refresh(shift)

                return shift


    async def finish_shift(
        self,
    ) -> bool:

        active = await self.get_active_shift()

        if active is None:
            return False

        async with SessionLocal() as session:

            shift = await session.get(
                Shift,
                active.id,
            )

            shift.ended_at = datetime.now()

            await session.commit()

            return True


shift_service = ShiftService()
