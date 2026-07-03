from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.active_machine_rail import ActiveMachineRail
from app.models.machine import Machine
from app.models.machine_rail import MachineRail
from app.models.shift import Shift
from app.models.user import User


class ActiveMachineRailService:
    async def get(
        self,
        shift_id: int,
        machine_id: int,
    ) -> ActiveMachineRail | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ActiveMachineRail)
                .options(
                    selectinload(ActiveMachineRail.machine),
                    selectinload(ActiveMachineRail.machine_rail).selectinload(
                        MachineRail.rail,
                    ),
                    selectinload(ActiveMachineRail.created_by),
                )
                .where(
                    ActiveMachineRail.shift_id == shift_id,
                    ActiveMachineRail.machine_id == machine_id,
                )
            )
            return result.scalar_one_or_none()

    async def get_by_shift(
        self,
        shift_id: int,
    ) -> list[ActiveMachineRail]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ActiveMachineRail)
                .options(
                    selectinload(ActiveMachineRail.machine),
                    selectinload(ActiveMachineRail.machine_rail).selectinload(
                        MachineRail.rail,
                    ),
                    selectinload(ActiveMachineRail.created_by),
                )
                .where(ActiveMachineRail.shift_id == shift_id)
                .join(ActiveMachineRail.machine)
                .order_by(Machine.name)
            )
            return list(result.scalars().all())

    async def set_active(
        self,
        shift: Shift,
        machine_rail: MachineRail,
        user: User,
    ) -> ActiveMachineRail:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ActiveMachineRail).where(
                    ActiveMachineRail.shift_id == shift.id,
                    ActiveMachineRail.machine_id == machine_rail.machine_id,
                )
            )
            active = result.scalar_one_or_none()

            if active is None:
                active = ActiveMachineRail(
                    shift_id=shift.id,
                    machine_id=machine_rail.machine_id,
                    machine_rail_id=machine_rail.id,
                    created_by_id=user.id,
                )
                session.add(active)
            else:
                active.machine_rail_id = machine_rail.id
                active.created_by_id = user.id

            await session.commit()
            await session.refresh(active)
            return active

    async def clear(
        self,
        shift_id: int,
        machine_id: int,
    ) -> bool:
        async with SessionLocal() as session:
            result = await session.execute(
                delete(ActiveMachineRail).where(
                    ActiveMachineRail.shift_id == shift_id,
                    ActiveMachineRail.machine_id == machine_id,
                )
            )
            await session.commit()
            return result.rowcount > 0


active_machine_rail_service = ActiveMachineRailService()
