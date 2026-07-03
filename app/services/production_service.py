from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.machine import Machine
from app.models.machine_rail import MachineRail
from app.models.production_entry import ProductionEntry
from app.models.rail import Rail
from app.models.shift import Shift
from app.models.user import User
from app.models.work_session import WorkSession


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def meters(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def whole_meters(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def guide_pay_multiplier(rail: Rail, rail_length: Decimal) -> int:
    if " Напр " not in rail.name:
        return 1

    if rail_length == Decimal("1.200"):
        return 2

    if rail_length == Decimal("2.400"):
        return 4

    return 1


class ProductionService:
    async def get_enabled_rails(self) -> list[Rail]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Rail)
                .join(MachineRail)
                .where(
                    Rail.is_active.is_(True),
                    MachineRail.is_enabled.is_(True),
                )
                .distinct()
                .order_by(Rail.name)
            )

            return list(result.scalars().all())

    async def get_enabled_rails_for_machine(
        self,
        machine_id: int,
    ) -> list[MachineRail]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(MachineRail)
                .options(selectinload(MachineRail.rail))
                .where(
                    MachineRail.machine_id == machine_id,
                    MachineRail.is_enabled.is_(True),
                )
                .join(MachineRail.rail)
                .order_by(Rail.name)
            )

            return list(result.scalars().all())

    async def get_enabled_machines_for_rail(
        self,
        rail_id: int,
    ) -> list[MachineRail]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(MachineRail)
                .options(selectinload(MachineRail.machine))
                .where(
                    MachineRail.rail_id == rail_id,
                    MachineRail.is_enabled.is_(True),
                )
                .join(MachineRail.machine)
                .order_by(Machine.name)
            )

            return list(result.scalars().all())

    async def create_entry(
        self,
        shift: Shift,
        machine_id: int,
        machine_rail_id: int,
        packs: int,
        created_by: User,
    ) -> tuple[ProductionEntry, Machine, Rail, Decimal, Decimal, int]:
        async with SessionLocal() as session:
            machine_rail = await session.get(
                MachineRail,
                machine_rail_id,
                options=[
                    selectinload(MachineRail.machine),
                    selectinload(MachineRail.rail),
                ],
            )

            if machine_rail is None or machine_rail.machine_id != machine_id:
                raise ValueError("Рейка не найдена для выбранного станка.")

            result = await session.execute(
                select(WorkSession)
                .options(selectinload(WorkSession.user))
                .where(
                    WorkSession.shift_id == shift.id,
                    WorkSession.machine_id == machine_id,
                    WorkSession.ended_at.is_(None),
                )
            )
            work_session = result.scalar_one_or_none()

            operator = work_session.user if work_session else None
            operator_name = operator.full_name if operator else "Оператор не указан"
            operator_id = operator.id if operator else None

            rail = machine_rail.rail
            pieces = packs * rail.pieces_per_pack
            rail_length = Decimal(str(rail.length))
            operator_price = Decimal(str(machine_rail.operator_price))
            mechanic_price = Decimal(str(machine_rail.mechanic_price))
            payable_pieces = pieces * guide_pay_multiplier(rail, rail_length)

            total_meters = meters(Decimal(pieces) * rail_length)
            operator_total = money(
                Decimal(payable_pieces) / Decimal(1000) * operator_price
            )
            mechanic_total = money(
                Decimal(payable_pieces) / Decimal(1000) * mechanic_price
            )

            entry = ProductionEntry(
                shift_id=shift.id,
                machine_id=machine_id,
                rail_id=rail.id,
                operator_name=operator_name,
                operator_id=operator_id,
                packs=packs,
                pieces=pieces,
                meters=total_meters,
                operator_price=operator_price,
                mechanic_price=mechanic_price,
                operator_total=operator_total,
                mechanic_total=mechanic_total,
                rail_length=rail_length,
                pieces_per_pack=rail.pieces_per_pack,
                is_deleted=False,
            )

            session.add(entry)
            await session.commit()
            await session.refresh(entry)

            return (
                entry,
                machine_rail.machine,
                rail,
                operator_total,
                mechanic_total,
                payable_pieces,
            )


production_service = ProductionService()
