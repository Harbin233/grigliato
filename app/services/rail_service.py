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

    async def get_by_name(self, name: str):
        async with SessionLocal() as session:
            result = await session.execute(
                select(Rail).where(Rail.name == name)
            )

            return result.scalar_one_or_none()

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

    async def clone_shape_from_source(
        self,
        source_rail_id: int,
        target_shape: str,
    ) -> Rail | None:
        async with SessionLocal() as session:
            source = await session.get(Rail, source_rail_id)

            if source is None:
                return None

            parts = source.name.split(" ", maxsplit=2)

            if len(parts) != 3:
                return None

            rail_class, _rail_shape, rail_base_name = parts
            allowed_shapes = {
                "Эконом": {"Мама", "Папа"},
                "GL": {"Мама", "Папа", "L"},
            }.get(rail_class, set())

            if target_shape not in allowed_shapes:
                return None

            target_name = f"{rail_class} {target_shape} {rail_base_name}"
            result = await session.execute(
                select(Rail).where(Rail.name == target_name)
            )
            target = result.scalar_one_or_none()

            if target is None:
                target = Rail(
                    name=target_name,
                    length=source.length,
                    pieces_per_pack=source.pieces_per_pack,
                    metal=source.metal,
                    is_active=True,
                )
                session.add(target)
                await session.flush()
            else:
                target.length = source.length
                target.pieces_per_pack = source.pieces_per_pack
                target.metal = source.metal
                target.is_active = True

            source_rates = (
                await session.execute(
                    select(MachineRail).where(
                        MachineRail.rail_id == source.id
                    )
                )
            ).scalars().all()
            existing_target_rates = {
                row.machine_id: row
                for row in (
                    await session.execute(
                        select(MachineRail).where(
                            MachineRail.rail_id == target.id
                        )
                    )
                ).scalars().all()
            }
            source_machine_ids = {
                source_rate.machine_id
                for source_rate in source_rates
            }

            for source_rate in source_rates:
                target_rate = existing_target_rates.get(source_rate.machine_id)

                if target_rate:
                    target_rate.operator_price = source_rate.operator_price
                    target_rate.mechanic_price = source_rate.mechanic_price
                    target_rate.is_enabled = source_rate.is_enabled
                    continue

                session.add(
                    MachineRail(
                        machine_id=source_rate.machine_id,
                        rail_id=target.id,
                        operator_price=source_rate.operator_price,
                        mechanic_price=source_rate.mechanic_price,
                        is_enabled=source_rate.is_enabled,
                    )
                )

            for machine_id, target_rate in existing_target_rates.items():
                if machine_id not in source_machine_ids:
                    target_rate.is_enabled = False

            await session.commit()
            await session.refresh(target)

            return target

    async def clone_pair_from_source(self, source_rail_id: int) -> Rail | None:
        async with SessionLocal() as session:
            source = await session.get(Rail, source_rail_id)

            if source is None:
                return None

            parts = source.name.split(" ", maxsplit=2)

            if len(parts) != 3:
                return None

            _rail_class, rail_shape, _rail_base_name = parts
            pair_shape = {
                "Мама": "Папа",
                "Папа": "Мама",
            }.get(rail_shape)

        if pair_shape is None:
            return None

        return await self.clone_shape_from_source(source_rail_id, pair_shape)

    async def create_with_rates_for_all_machines(
        self,
        name: str,
        length: Decimal,
        pieces_per_pack: int,
        machine_rates: list[dict],
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

            rates_by_machine_id = {
                rate["machine_id"]: rate
                for rate in machine_rates
            }
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
                new_rate = rates_by_machine_id.get(machine.id)

                if rate:
                    if new_rate is None:
                        rate.is_enabled = False
                    else:
                        rate.operator_price = new_rate["operator_price"]
                        rate.mechanic_price = new_rate["mechanic_price"]
                        rate.is_enabled = True
                    continue

                if new_rate is None:
                    continue

                session.add(
                    MachineRail(
                        machine_id=machine.id,
                        rail_id=rail.id,
                        operator_price=new_rate["operator_price"],
                        mechanic_price=new_rate["mechanic_price"],
                        is_enabled=True,
                    )
                )

            await session.commit()
            await session.refresh(rail)

            return rail


rail_service = RailService()
