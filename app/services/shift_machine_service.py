from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.machine import Machine
from app.models.shift_machine_assignment import ShiftMachineAssignment


class ShiftMachineService:
    async def get_for_user(
        self,
        shift_id: int,
        user_id: int,
    ) -> list[ShiftMachineAssignment]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ShiftMachineAssignment)
                .options(selectinload(ShiftMachineAssignment.machine))
                .where(
                    ShiftMachineAssignment.shift_id == shift_id,
                    ShiftMachineAssignment.user_id == user_id,
                )
                .join(ShiftMachineAssignment.machine)
                .order_by(Machine.name)
            )

            return list(result.scalars().all())

    async def get_by_shift(
        self,
        shift_id: int,
    ) -> list[ShiftMachineAssignment]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ShiftMachineAssignment)
                .options(
                    selectinload(ShiftMachineAssignment.machine),
                    selectinload(ShiftMachineAssignment.user),
                )
                .where(ShiftMachineAssignment.shift_id == shift_id)
                .join(ShiftMachineAssignment.machine)
                .order_by(Machine.name)
            )

            return list(result.scalars().all())

    async def get_machine_assignment(
        self,
        shift_id: int,
        machine_id: int,
    ) -> ShiftMachineAssignment | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ShiftMachineAssignment)
                .options(
                    selectinload(ShiftMachineAssignment.machine),
                    selectinload(ShiftMachineAssignment.user),
                )
                .where(
                    ShiftMachineAssignment.shift_id == shift_id,
                    ShiftMachineAssignment.machine_id == machine_id,
                )
            )

            return result.scalar_one_or_none()

    async def assign(
        self,
        shift_id: int,
        user_id: int,
        machine_id: int,
    ) -> tuple[bool, str]:
        async with SessionLocal() as session:
            existing = (
                await session.execute(
                    select(ShiftMachineAssignment)
                    .options(selectinload(ShiftMachineAssignment.user))
                    .where(
                        ShiftMachineAssignment.shift_id == shift_id,
                        ShiftMachineAssignment.machine_id == machine_id,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                if existing.user_id == user_id:
                    return True, "Станок уже в вашем списке."

                return (
                    False,
                    f"Станок уже закреплен за {existing.user.full_name}.",
                )

            assignment = ShiftMachineAssignment(
                shift_id=shift_id,
                user_id=user_id,
                machine_id=machine_id,
            )
            session.add(assignment)
            await session.commit()

            return True, "Станок добавлен в ваш список."

    async def unassign(
        self,
        shift_id: int,
        user_id: int,
        machine_id: int,
    ) -> bool:
        async with SessionLocal() as session:
            result = await session.execute(
                delete(ShiftMachineAssignment).where(
                    ShiftMachineAssignment.shift_id == shift_id,
                    ShiftMachineAssignment.user_id == user_id,
                    ShiftMachineAssignment.machine_id == machine_id,
                )
            )
            await session.commit()

            return result.rowcount > 0


shift_machine_service = ShiftMachineService()
