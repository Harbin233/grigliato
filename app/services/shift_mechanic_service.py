from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.shift_mechanic import ShiftMechanic, MechanicType


class ShiftMechanicService:

    async def assign(
        self,
        shift_id: int,
        user_id: int,
        mechanic_type: MechanicType,
    ):
        async with SessionLocal() as session:
            mechanic = ShiftMechanic(
                shift_id=shift_id,
                user_id=user_id,
                mechanic_type=mechanic_type,
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
