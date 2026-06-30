from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.machine import Machine


class MachineService:

    async def get_all(self):
        async with SessionLocal() as session:
            result = await session.execute(
                select(Machine)
                .where(Machine.is_active.is_(True))
                .order_by(Machine.name)
            )

            return result.scalars().all()

    async def get(self, machine_id: int):
        async with SessionLocal() as session:
            return await session.get(Machine, machine_id)

    async def create(
        self,
        name: str,
        machine_type: str,
    ):
        async with SessionLocal() as session:
            machine = Machine(
                name=name,
                machine_type=machine_type,
                is_active=True,
            )

            session.add(machine)
            await session.commit()
            await session.refresh(machine)

            return machine


machine_service = MachineService()
