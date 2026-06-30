from datetime import datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.machine import Machine
from app.models.shift import Shift
from app.models.user import User
from app.models.work_session import WorkSession


class WorkSessionService:

    async def get_active(self, user_id: int) -> WorkSession | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(WorkSession).where(
                    WorkSession.user_id == user_id,
                    WorkSession.ended_at.is_(None),
                )
            )
            return result.scalar_one_or_none()

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
    ) -> WorkSession:

        async with SessionLocal() as session:

            work = WorkSession(
                user_id=user.id,
                shift_id=shift.id,
                machine_id=machine_id,
                started_at=datetime.now(),
            )

            session.add(work)

            await session.commit()
            await session.refresh(work)

            return work

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


work_session_service = WorkSessionService()
