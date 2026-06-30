from sqlalchemy import select

from app.core.constants import MACHINES
from app.db.session import SessionLocal
from app.models.machine import Machine


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


async def initialize_reference_data() -> None:
    await ensure_machines()
