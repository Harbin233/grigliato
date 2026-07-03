from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.machine import Machine
from app.models.shift import Shift
from app.models.user import User
from app.models.work_session import WorkSession


class WorkSessionService:

    async def get_active(self, user_id: int) -> WorkSession | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(WorkSession)
                .options(
                    selectinload(WorkSession.machine),
                    selectinload(WorkSession.shift),
                )
                .where(
                    WorkSession.user_id == user_id,
                    WorkSession.ended_at.is_(None),
                )
            )
            return result.scalar_one_or_none()

    async def get_active_by_machine(
        self,
        shift_id: int,
        machine_id: int,
    ) -> WorkSession | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(WorkSession)
                .options(
                    selectinload(WorkSession.user),
                    selectinload(WorkSession.machine),
                )
                .where(
                    WorkSession.shift_id == shift_id,
                    WorkSession.machine_id == machine_id,
                    WorkSession.ended_at.is_(None),
                )
            )

            return result.scalar_one_or_none()

    async def get_active_by_shift(
        self,
        shift_id: int,
    ) -> list[WorkSession]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(WorkSession)
                .options(
                    selectinload(WorkSession.user),
                    selectinload(WorkSession.machine),
                )
                .where(
                    WorkSession.shift_id == shift_id,
                    WorkSession.ended_at.is_(None),
                )
                .join(WorkSession.machine)
                .order_by(Machine.name)
            )

            return list(result.scalars().all())

    async def get_machines(self) -> list[Machine]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Machine)
                .where(Machine.is_active.is_(True))
                .order_by(Machine.name)
            )
            return list(result.scalars().all())

    async def start(
        self,
        user: User,
        shift: Shift,
        machine_id: int,
        is_overtime: bool = False,
    ) -> tuple[bool, str]:
        active_for_user = await self.get_active(user.id)

        if active_for_user:
            overtime_text = (
                "\nПодработка: да"
                if active_for_user.is_overtime
                else ""
            )
            return (
                True,
                f"Вы уже работаете на станке {active_for_user.machine.name}."
                f"{overtime_text}",
            )

        active_for_machine = await self.get_active_by_machine(
            shift.id,
            machine_id,
        )

        if active_for_machine:
            return (
                False,
                "Станок уже занят оператором "
                f"{active_for_machine.user.full_name}.",
            )

        async with SessionLocal() as session:

            work = WorkSession(
                user_id=user.id,
                shift_id=shift.id,
                machine_id=machine_id,
                started_at=datetime.now(),
                is_overtime=is_overtime,
            )

            session.add(work)

            await session.commit()
            await session.refresh(work)

            machine = await session.get(Machine, machine_id)
            overtime_text = "\nПодработка: да" if is_overtime else ""

            return (
                True,
                f"Вы приступили к работе на станке {machine.name}."
                f"{overtime_text}",
            )

    async def finish(
        self,
        user_id: int,
    ) -> bool:

        async with SessionLocal() as session:

            result = await session.execute(
                select(WorkSession).where(
                    WorkSession.user_id == user_id,
                    WorkSession.ended_at.is_(None),
                )
            )

            work = result.scalar_one_or_none()

            if work is None:
                return False

            work.ended_at = datetime.now()

            await session.commit()

            return True

    async def finish_by_id(
        self,
        work_session_id: int,
        shift_id: int,
    ) -> WorkSession | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(WorkSession)
                .options(
                    selectinload(WorkSession.user),
                    selectinload(WorkSession.machine),
                )
                .where(
                    WorkSession.id == work_session_id,
                    WorkSession.shift_id == shift_id,
                    WorkSession.ended_at.is_(None),
                )
            )
            work = result.scalar_one_or_none()

            if work is None:
                return None

            work.ended_at = datetime.now()
            await session.commit()
            await session.refresh(work)

            return work

    async def finish_by_shift(
        self,
        shift_id: int,
    ) -> int:
        async with SessionLocal() as session:
            result = await session.execute(
                update(WorkSession)
                .where(
                    WorkSession.shift_id == shift_id,
                    WorkSession.ended_at.is_(None),
                )
                .values(ended_at=datetime.now())
            )
            await session.commit()

            return result.rowcount


work_session_service = WorkSessionService()
