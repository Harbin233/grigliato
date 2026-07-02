from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.machine import Machine
from app.models.machine_rail import MachineRail
from app.models.rail import Rail
from app.models.rail import MetalType


class RailService:

    async def get_all(self):
        async with SessionLocal() as session:
            result = await session.execute(
                select(Rail)
                .where(Rail.is_active.is_(True))
                .order_by(Rail.name)
            )

            return result.scalars().all()

    async def get(self, rail_id: int):
        async with SessionLocal() as session:
            return await session.get(Rail, rail_id)

    async def create(
        self,
        name: str,
        length,
        pieces_per_pack: int,
        metal,
    ):
        async with SessionLocal() as session:
            rail = Rail(
                name=name,
                length=length,
                pieces_per_pack=pieces_per_pack,
                metal=metal,
                is_active=True,
            )

            session.add(rail)
            await session.commit()
            await session.refresh(rail)

            return rail

    async def create_with_rates_for_all_machines(
        self,
        name: str,
        length: Decimal,
        pieces_per_pack: int,
        operator_price: Decimal,
        mechanic_price: Decimal,
    ) -> Rail:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Rail).where(Rail.name == name)
            )
            rail = result.scalar_one_or_none()

            if rail is None:
                rail = Rail(
                    name=name,
                    length=length,
                    pieces_per_pack=pieces_per_pack,
                    metal=MetalType.ZINC,
                    is_active=True,
                )
                session.add(rail)
                await session.flush()
            else:
                rail.length = length
                rail.pieces_per_pack = pieces_per_pack
                rail.is_active = True

            machines = (
                await session.execute(
                    select(Machine).where(Machine.is_active.is_(True))
                )
            ).scalars().all()

            existing_rates = {
                row.machine_id: row
                for row in (
                    await session.execute(
                        select(MachineRail).where(MachineRail.rail_id == rail.id)
                    )
                ).scalars().all()
            }

            for machine in machines:
                rate = existing_rates.get(machine.id)

                if rate:
                    rate.operator_price = operator_price
                    rate.mechanic_price = mechanic_price
                    rate.is_enabled = True
                    continue

                session.add(
                    MachineRail(
                        machine_id=machine.id,
                        rail_id=rail.id,
                        operator_price=operator_price,
                        mechanic_price=mechanic_price,
                        is_enabled=True,
                    )
                )

            await session.commit()
            await session.refresh(rail)

            return rail


rail_service = RailService()
