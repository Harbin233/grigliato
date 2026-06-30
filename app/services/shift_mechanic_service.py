from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.shift_mechanic import ShiftMechanic, MechanicType


class ShiftMechanicService:
    async def get_by_shift_and_user(
        self,
        shift_id: int,
        user_id: int,
    ) -> ShiftMechanic | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ShiftMechanic).where(
                    ShiftMechanic.shift_id == shift_id,
                    ShiftMechanic.user_id == user_id,
                )
            )

            return result.scalar_one_or_none()

    async def count_main(
        self,
        shift_id: int,
        exclude_user_id: int | None = None,
    ) -> int:
        mechanics = await self.get_by_shift(shift_id)
        return sum(
            1
            for mechanic in mechanics
            if mechanic.mechanic_type == MechanicType.MAIN
            and mechanic.user_id != exclude_user_id
        )

    async def assign(
        self,
        shift_id: int,
        user_id: int,
        mechanic_type: MechanicType,
        is_overtime: bool = False,
    ):
        async with SessionLocal() as session:
            result = await session.execute(
                select(ShiftMechanic).where(
                    ShiftMechanic.shift_id == shift_id,
                    ShiftMechanic.user_id == user_id,
                )
            )
            mechanic = result.scalar_one_or_none()

            if mechanic:
                mechanic.mechanic_type = mechanic_type
                mechanic.is_overtime = is_overtime
                await session.commit()
                await session.refresh(mechanic)
                return mechanic

            mechanic = ShiftMechanic(
                shift_id=shift_id,
                user_id=user_id,
                mechanic_type=mechanic_type,
                is_overtime=is_overtime,
            )

            session.add(mechanic)
            await session.commit()
            await session.refresh(mechanic)

            return mechanic

    async def get_by_shift(self, shift_id: int):
        async with SessionLocal() as session:
            result = await session.execute(
                select(ShiftMechanic).where(
                    ShiftMechanic.shift_id == shift_id
                )
            )

            return result.scalars().all()

    async def get_main(self, shift_id: int):
        async with SessionLocal() as session:
            result = await session.execute(
                select(ShiftMechanic).where(
                    ShiftMechanic.shift_id == shift_id,
                    ShiftMechanic.mechanic_type == MechanicType.MAIN,
                )
            )

            return result.scalar_one_or_none()

    async def get_assistant(self, shift_id: int):
        async with SessionLocal() as session:
            result = await session.execute(
                select(ShiftMechanic).where(
                    ShiftMechanic.shift_id == shift_id,
                    ShiftMechanic.mechanic_type == MechanicType.ASSISTANT,
                )
            )

            return result.scalar_one_or_none()


shift_mechanic_service = ShiftMechanicService()
