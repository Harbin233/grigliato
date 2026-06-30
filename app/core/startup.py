from decimal import Decimal

from sqlalchemy import select

from app.core.constants import MACHINES
from app.db.session import SessionLocal
from app.models.machine import Machine
from app.models.machine_rail import MachineRail
from app.models.rail import MetalType, Rail


DEFAULT_RAIL_NAME = "Рейка эконом 50x40x10 0.6м 312шт"
DEFAULT_OPERATOR_PRICE = Decimal("199.18")
DEFAULT_MECHANIC_PRICE = Decimal("93.25")


async def ensure_machines() -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Machine.name)
        )
        existing_names = set(result.scalars().all())

        for machine_name in MACHINES:
            if machine_name in existing_names:
                continue

            session.add(
                Machine(
                    name=machine_name,
                    machine_type="grigliato",
                    is_active=True,
                )
            )

        await session.commit()


async def ensure_default_rail_rates() -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Rail).where(Rail.name == DEFAULT_RAIL_NAME)
        )
        rail = result.scalar_one_or_none()

        if rail is None:
            rail = Rail(
                name=DEFAULT_RAIL_NAME,
                length=Decimal("0.6"),
                pieces_per_pack=312,
                metal=MetalType.ZINC,
                is_active=True,
            )
            session.add(rail)
            await session.flush()

        machines = (
            await session.execute(
                select(Machine).where(Machine.is_active.is_(True))
            )
        ).scalars().all()

        existing_pairs = {
            tuple(row)
            for row in (
                await session.execute(
                    select(MachineRail.machine_id, MachineRail.rail_id)
                    .where(MachineRail.rail_id == rail.id)
                )
            ).all()
        }

        for machine in machines:
            pair = (machine.id, rail.id)

            if pair in existing_pairs:
                continue

            session.add(
                MachineRail(
                    machine_id=machine.id,
                    rail_id=rail.id,
                    operator_price=DEFAULT_OPERATOR_PRICE,
                    mechanic_price=DEFAULT_MECHANIC_PRICE,
                    is_enabled=True,
                )
            )

        await session.commit()


async def initialize_reference_data() -> None:
    await ensure_machines()
    await ensure_default_rail_rates()
