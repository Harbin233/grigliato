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

    async def get_enabled_machine_rail(
        self,
        machine_id: int,
        rail_id: int,
    ) -> MachineRail | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(MachineRail)
                .options(
                    selectinload(MachineRail.machine),
                    selectinload(MachineRail.rail),
                )
                .where(
                    MachineRail.machine_id == machine_id,
                    MachineRail.rail_id == rail_id,
                    MachineRail.is_enabled.is_(True),
                )
            )

            return result.scalar_one_or_none()

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

    async def machine_shift_summary(
        self,
        shift_id: int,
        machine_id: int,
    ) -> dict:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ProductionEntry, Rail)
                    .join(Rail, ProductionEntry.rail_id == Rail.id)
                    .where(
                        ProductionEntry.shift_id == shift_id,
                        ProductionEntry.machine_id == machine_id,
                        ProductionEntry.is_deleted.is_(False),
                    )
                    .order_by(ProductionEntry.created_at)
                )
            ).all()

            summary = {
                "packs": 0,
                "pieces": 0,
                "meters": Decimal("0"),
                "operator_total": Decimal("0"),
                "mechanic_total": Decimal("0"),
                "types": {},
                "entries_count": len(rows),
            }

            for entry, rail in rows:
                rail_type = rail.name.split(" ", maxsplit=1)[0]
                type_summary = summary["types"].setdefault(
                    rail_type,
                    {
                        "packs": 0,
                        "pieces": 0,
                        "meters": Decimal("0"),
                        "operator_total": Decimal("0"),
                        "mechanic_total": Decimal("0"),
                    },
                )

                entry_meters = Decimal(str(entry.meters))
                entry_operator_total = Decimal(str(entry.operator_total))
                entry_mechanic_total = Decimal(str(entry.mechanic_total))

                summary["packs"] += entry.packs
                summary["pieces"] += entry.pieces
                summary["meters"] += entry_meters
                summary["operator_total"] += entry_operator_total
                summary["mechanic_total"] += entry_mechanic_total

                type_summary["packs"] += entry.packs
                type_summary["pieces"] += entry.pieces
                type_summary["meters"] += entry_meters
                type_summary["operator_total"] += entry_operator_total
                type_summary["mechanic_total"] += entry_mechanic_total

            return summary

    async def shift_report(self, shift_id: int) -> dict:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ProductionEntry, Rail, Machine)
                    .join(Rail, ProductionEntry.rail_id == Rail.id)
                    .join(Machine, ProductionEntry.machine_id == Machine.id)
                    .where(
                        ProductionEntry.shift_id == shift_id,
                        ProductionEntry.is_deleted.is_(False),
                    )
                    .order_by(Machine.name, ProductionEntry.created_at)
                )
            ).all()

            report = {
                "packs": 0,
                "pieces": 0,
                "meters": Decimal("0"),
                "operator_total": Decimal("0"),
                "mechanic_total": Decimal("0"),
                "entries_count": len(rows),
                "types": {},
                "machines": {},
                "production_machine_ids": set(),
            }

            for entry, rail, machine in rows:
                rail_type = rail.name.split(" ", maxsplit=1)[0]
                entry_meters = Decimal(str(entry.meters))
                entry_operator_total = Decimal(str(entry.operator_total))
                entry_mechanic_total = Decimal(str(entry.mechanic_total))

                report["packs"] += entry.packs
                report["pieces"] += entry.pieces
                report["meters"] += entry_meters
                report["operator_total"] += entry_operator_total
                report["mechanic_total"] += entry_mechanic_total
                report["production_machine_ids"].add(machine.id)

                for bucket in (
                    report["types"].setdefault(
                        rail_type,
                        self._empty_summary(),
                    ),
                    report["machines"].setdefault(
                        machine.id,
                        {
                            **self._empty_summary(),
                            "machine_name": machine.name,
                            "types": {},
                        },
                    ),
                ):
                    bucket["packs"] += entry.packs
                    bucket["pieces"] += entry.pieces
                    bucket["meters"] += entry_meters
                    bucket["operator_total"] += entry_operator_total
                    bucket["mechanic_total"] += entry_mechanic_total

                machine_summary = report["machines"][machine.id]
                type_summary = machine_summary["types"].setdefault(
                    rail_type,
                    self._empty_summary(),
                )
                type_summary["packs"] += entry.packs
                type_summary["pieces"] += entry.pieces
                type_summary["meters"] += entry_meters
                type_summary["operator_total"] += entry_operator_total
                type_summary["mechanic_total"] += entry_mechanic_total

            return report

    @staticmethod
    def _empty_summary() -> dict:
        return {
            "packs": 0,
            "pieces": 0,
            "meters": Decimal("0"),
            "operator_total": Decimal("0"),
            "mechanic_total": Decimal("0"),
        }


production_service = ProductionService()
