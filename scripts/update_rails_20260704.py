import asyncio
from decimal import Decimal

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.active_machine_rail import ActiveMachineRail
from app.models.machine import Machine
from app.models.machine_rail import MachineRail
from app.models.production_entry import ProductionEntry
from app.models.rail import MetalType, Rail


GUIDE_PACKS_GRIGLIATO = {
    "0.6": 500,
    "1.2": 300,
    "2.40": 200,
}
GUIDE_PACKS_PYRAMID_35 = {
    "0.6": 150,
    "1.2": 51,
    "2.40": 40,
}
GUIDE_PACKS_PYRAMID_425 = {
    "0.6": 108,
    "1.2": 42,
    "2.40": 30,
}
GRIGLIATO_RATE_GROUPS = {
    "30x30": (("Г-1", "Г-2", "Г-4"), "116.56", "264.81"),
    "50x50": (("Г-1", "Г-2", "Г-4"), "75.54", "171.61"),
    "75x75": (("Г-1", "Г-2", "Г-4"), "75.54", "171.61"),
    "100x100": (("Г-1", "Г-2", "Г-4"), "75.54", "171.61"),
    "150x150": (("Г-1", "Г-2", "Г-4"), "75.54", "171.61"),
    "200x200": (("Г-1", "Г-2", "Г-4"), "69.94", "158.89"),
}
GL15_30_RATE_GROUPS = [
    (("Г-1", "Г-2", "Г-4"), "167.85", "327.68"),
]


async def get_rail(session, name: str) -> Rail | None:
    return (
        await session.execute(select(Rail).where(Rail.name == name))
    ).scalar_one_or_none()


async def upsert_rail(
    session,
    name: str,
    length: str,
    pieces_per_pack: int,
) -> Rail:
    rail = await get_rail(session, name)

    if rail is None:
        rail = Rail(
            name=name,
            length=Decimal(length),
            pieces_per_pack=pieces_per_pack,
            metal=MetalType.ZINC,
            is_active=True,
        )
        session.add(rail)
        await session.flush()
        print("created rail", rail.id, name)
        return rail

    rail.length = Decimal(length)
    rail.pieces_per_pack = pieces_per_pack
    rail.is_active = True
    print("updated rail", rail.id, name)
    return rail


async def set_rates(
    session,
    rail: Rail,
    groups: list[tuple[tuple[str, ...], str, str]],
) -> None:
    machines = {
        machine.name: machine
        for machine in (
            await session.execute(select(Machine))
        ).scalars().all()
    }
    target_rates = {
        row.machine_id: row
        for row in (
            await session.execute(
                select(MachineRail).where(MachineRail.rail_id == rail.id)
            )
        ).scalars().all()
    }
    enabled_machine_ids: set[int] = set()

    for machine_names, mechanic_price, operator_price in groups:
        for machine_name in machine_names:
            machine = machines.get(machine_name)

            if machine is None:
                raise RuntimeError(f"Machine not found: {machine_name}")

            enabled_machine_ids.add(machine.id)
            target_rate = target_rates.get(machine.id)

            if target_rate:
                target_rate.operator_price = Decimal(operator_price)
                target_rate.mechanic_price = Decimal(mechanic_price)
                target_rate.is_enabled = True
                continue

            session.add(
                MachineRail(
                    rail_id=rail.id,
                    machine_id=machine.id,
                    operator_price=Decimal(operator_price),
                    mechanic_price=Decimal(mechanic_price),
                    is_enabled=True,
                )
            )

    for machine_id, target_rate in target_rates.items():
        if machine_id not in enabled_machine_ids:
            target_rate.is_enabled = False


async def copy_rates(session, source: Rail, target: Rail, *, enabled: bool | None = None) -> None:
    source_rates = (
        await session.execute(
            select(MachineRail).where(MachineRail.rail_id == source.id)
        )
    ).scalars().all()
    target_rates = {
        row.machine_id: row
        for row in (
            await session.execute(
                select(MachineRail).where(MachineRail.rail_id == target.id)
            )
        ).scalars().all()
    }
    source_machine_ids = {rate.machine_id for rate in source_rates}

    for source_rate in source_rates:
        target_rate = target_rates.get(source_rate.machine_id)
        is_enabled = source_rate.is_enabled if enabled is None else enabled

        if target_rate:
            target_rate.operator_price = source_rate.operator_price
            target_rate.mechanic_price = source_rate.mechanic_price
            target_rate.is_enabled = is_enabled
            continue

        session.add(
            MachineRail(
                rail_id=target.id,
                machine_id=source_rate.machine_id,
                operator_price=source_rate.operator_price,
                mechanic_price=source_rate.mechanic_price,
                is_enabled=is_enabled,
            )
        )

    for machine_id, target_rate in target_rates.items():
        if machine_id not in source_machine_ids:
            target_rate.is_enabled = False


async def merge_rails(session, source: Rail, target: Rail) -> None:
    await session.execute(
        update(ProductionEntry)
        .where(ProductionEntry.rail_id == source.id)
        .values(rail_id=target.id)
    )
    source_rates = (
        await session.execute(
            select(MachineRail).where(MachineRail.rail_id == source.id)
        )
    ).scalars().all()

    for source_rate in source_rates:
        target_rate = (
            await session.execute(
                select(MachineRail).where(
                    MachineRail.rail_id == target.id,
                    MachineRail.machine_id == source_rate.machine_id,
                )
            )
        ).scalar_one_or_none()

        if target_rate:
            await session.execute(
                update(ActiveMachineRail)
                .where(ActiveMachineRail.machine_rail_id == source_rate.id)
                .values(machine_rail_id=target_rate.id)
            )
            source_rate.is_enabled = False
            continue

        source_rate.rail_id = target.id

    source.is_active = False
    print("merged rail", source.id, source.name, "->", target.id, target.name)


async def rename_rail(session, old_name: str, new_name: str) -> Rail | None:
    source = await get_rail(session, old_name)

    if source is None:
        return await get_rail(session, new_name)

    target = await get_rail(session, new_name)

    if target is None:
        source.name = new_name
        source.is_active = True
        print("renamed rail", source.id, old_name, "->", new_name)
        return source

    await merge_rails(session, source, target)
    return target


async def copy_from_gl15(
    session,
    target_name: str,
    source_name: str,
    length: str,
    pieces_per_pack: int,
) -> Rail:
    source = await get_rail(session, source_name)

    if source is None:
        raise RuntimeError(f"Source GL15 rail not found: {source_name}")

    target = await upsert_rail(session, target_name, length, pieces_per_pack)
    await copy_rates(session, source, target)
    return target


async def update_grigliato(session) -> None:
    cells = ["30x30", "50x50", "75x75", "100x100", "150x150", "200x200"]

    for cell in cells:
        base = f"{cell} h30 b5"
        rate_groups = [GRIGLIATO_RATE_GROUPS[cell]]

        for shape in ("Мама", "Папа"):
            rail = await upsert_rail(session, f"Grigliato {shape} {base}", "0.6", 500)
            await set_rates(session, rail, rate_groups)

        for length, pack in GUIDE_PACKS_GRIGLIATO.items():
            rail = await upsert_rail(
                session,
                f"Grigliato Напр {base} {length}м",
                length,
                pack,
            )
            await set_rates(session, rail, rate_groups)


async def update_gl15_30(session) -> None:
    for shape in ("Мама", "Папа"):
        rail = await upsert_rail(
            session,
            f"GL15 {shape} 30x30 h47 b15",
            "0.6",
            160,
        )
        await set_rates(session, rail, GL15_30_RATE_GROUPS)


async def update_pyramid_35(session) -> None:
    old_cells = ["50x50", "60x60", "75x75", "86x86", "100x100", "120x120", "150x150", "200x200", "300x300"]

    for cell in old_cells:
        for shape in ("Мама", "Папа", "Напр"):
            if shape == "Напр":
                for length in ("0.6", "1.2", "2.40"):
                    await rename_rail(
                        session,
                        f"Пирамида {shape} {cell} h37 b15 {length}м",
                        f"Пирамида {shape} {cell} h35 b10 {length}м",
                    )
                continue

            await rename_rail(
                session,
                f"Пирамида {shape} {cell} h37 b15",
                f"Пирамида {shape} {cell} h35 b10",
            )

    cells_35 = ["50x50", "75x75", "86x86", "100x100", "120x120", "150x150", "200x200", "300x300"]

    for cell in cells_35:
        source_cell = cell if cell != "300x300" else "200x200"

        for shape in ("Мама", "Папа"):
            source = f"GL15 {shape} {source_cell} h37 b15"
            await copy_from_gl15(
                session,
                f"Пирамида {shape} {cell} h35 b10",
                source,
                "0.6",
                150,
            )

        for length, pack in GUIDE_PACKS_PYRAMID_35.items():
            await copy_from_gl15(
                session,
                f"Пирамида Напр {cell} h35 b10 {length}м",
                f"GL15 Мама {source_cell} h37 b15",
                length,
                pack,
            )


async def update_pyramid_425(session) -> None:
    cells = ["50x50", "60x60", "75x75", "86x86", "100x100", "120x120", "150x150", "200x200", "300x300"]

    for cell in cells:
        for shape in ("Мама", "Папа"):
            source_cell = cell if cell != "300x300" else "200x200"
            await copy_from_gl15(
                session,
                f"Пирамида {shape} {cell} h42.5 b10",
                f"GL15 {shape} {source_cell} h37 b15",
                "0.6",
                108,
            )

        source_cell = cell if cell != "300x300" else "200x200"
        for length, pack in GUIDE_PACKS_PYRAMID_425.items():
            await copy_from_gl15(
                session,
                f"Пирамида Напр {cell} h42.5 b10 {length}м",
                f"GL15 Мама {source_cell} h37 b15",
                length,
                pack,
            )


async def update_gl24(session) -> None:
    cells = ["50x50", "60x60", "75x75", "86x86", "100x100", "120x120", "150x150", "200x200"]

    for cell in cells:
        for shape in ("Мама", "Папа", "L"):
            await copy_from_gl15(
                session,
                f"GL24 {shape} {cell} h34 b24",
                f"GL15 {shape} {cell} h37 b15",
                "0.6",
                154,
            )


async def main() -> None:
    async with SessionLocal() as session:
        await update_grigliato(session)
        await update_gl15_30(session)
        await update_pyramid_35(session)
        await update_pyramid_425(session)
        await update_gl24(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
