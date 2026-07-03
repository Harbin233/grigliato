import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.machine import Machine
from app.models.machine_rail import MachineRail
from app.models.rail import MetalType, Rail


GUIDE_LENGTHS = ["0.6", "1.2", "2.40"]


def rail_names(rail_class: str, shapes: list[str], base_name: str) -> list[str]:
    names = []

    for shape in shapes:
        if shape == "Напр":
            for length in GUIDE_LENGTHS:
                names.append(f"{rail_class} {shape} {base_name} {length}м")
        else:
            names.append(f"{rail_class} {shape} {base_name}")

    return names


def rows() -> list[dict]:
    return [
        {
            "rail_class": "Grigliato",
            "shapes": ["Мама", "Папа", "Напр"],
            "bases": ["30x30 h30 b5"],
            "length": "0.6",
            "pieces_per_pack": 1,
            "rates_enabled": False,
            "rates": [(["Г-1", "Г-2", "Г-4"], "167.85", "327.68")],
        },
        {
            "rail_class": "GL",
            "shapes": ["Мама", "Папа"],
            "bases": ["30x30 h47 b15"],
            "length": "0.6",
            "pieces_per_pack": 1,
            "rates_enabled": False,
            "rates": [(["Г-1", "Г-2", "Г-4"], "167.85", "327.68")],
        },
        {
            "rail_class": "Grigliato",
            "shapes": ["Мама", "Папа", "Напр"],
            "bases": [
                "50x50 h30 b5",
                "75x75 h30 b5",
                "100x100 h30 b5",
                "150x150 h30 b5",
            ],
            "length": "0.6",
            "pieces_per_pack": 1,
            "rates_enabled": False,
            "rates": [(["Г-1", "Г-2", "Г-4"], "75.54", "171.61")],
        },
        {
            "rail_class": "Grigliato",
            "shapes": ["Мама", "Папа", "Напр"],
            "bases": ["200x200 h30 b5"],
            "length": "0.6",
            "pieces_per_pack": 1,
            "rates_enabled": False,
            "rates": [(["Г-1", "Г-2", "Г-4"], "69.94", "158.89")],
        },
        {
            "rail_class": "GL15",
            "shapes": ["Мама", "Папа", "L"],
            "bases": [
                "50x50 h37 b15",
                "75x75 h37 b15",
                "60x60 h37 b15",
                "86x86 h37 b15",
            ],
            "length": "0.6",
            "pieces_per_pack": 192,
            "rates_enabled": True,
            "rates": [
                (["Г-1", "Г-2", "Г-4"], "125.89", "293.34"),
                (["С-3", "С-4", "С-5", "С-6"], "125.89", "268.90"),
            ],
        },
        {
            "rail_class": "Пирамида",
            "shapes": ["Мама", "Папа", "Напр"],
            "bases": [
                "50x50 h37 b15",
                "75x75 h37 b15",
                "60x60 h37 b15",
                "86x86 h37 b15",
            ],
            "length": "0.6",
            "pieces_per_pack": 1,
            "rates_enabled": False,
            "rates": [
                (["Г-1", "Г-2", "Г-4"], "125.89", "293.34"),
                (["С-3", "С-4", "С-5", "С-6"], "125.89", "268.90"),
            ],
        },
        {
            "rail_class": "GL15",
            "shapes": ["Мама", "Папа", "L"],
            "bases": [
                "100x100 h37 b15",
                "120x120 h37 b15",
                "150x150 h37 b15",
                "200x200 h37 b15",
            ],
            "length": "0.6",
            "pieces_per_pack": 192,
            "rates_enabled": True,
            "rates": [
                (["Г-1", "Г-2", "Г-4"], "83.92", "212.97"),
                (["С-3", "С-4", "С-5", "С-6"], "83.92", "179.27"),
            ],
        },
        {
            "rail_class": "Пирамида",
            "shapes": ["Мама", "Папа", "Напр"],
            "bases": [
                "100x100 h37 b15",
                "120x120 h37 b15",
                "150x150 h37 b15",
                "200x200 h37 b15",
            ],
            "length": "0.6",
            "pieces_per_pack": 1,
            "rates_enabled": False,
            "rates": [
                (["Г-1", "Г-2", "Г-4"], "83.92", "212.97"),
                (["С-3", "С-4", "С-5", "С-6"], "83.92", "179.27"),
            ],
        },
        {
            "rail_class": "Пирамида",
            "shapes": ["Мама", "Папа", "Напр"],
            "bases": ["300x300 h37 b15"],
            "length": "0.6",
            "pieces_per_pack": 1,
            "rates_enabled": False,
            "rates": [
                (["Г-1", "Г-2", "Г-4"], "62.94", "140.55"),
                (["С-3", "С-4", "С-5", "С-6"], "62.94", "134.44"),
            ],
        },
    ]


async def upsert_rate(
    session,
    rail_id: int,
    machine_id: int,
    mechanic_price: Decimal,
    operator_price: Decimal,
    is_enabled: bool,
    keep_enabled_state: bool = False,
) -> bool:
    rate = (
        await session.execute(
            select(MachineRail).where(
                MachineRail.rail_id == rail_id,
                MachineRail.machine_id == machine_id,
            )
        )
    ).scalar_one_or_none()

    if rate is None:
        session.add(
            MachineRail(
                rail_id=rail_id,
                machine_id=machine_id,
                mechanic_price=mechanic_price,
                operator_price=operator_price,
                is_enabled=is_enabled,
            )
        )
        return True

    rate.mechanic_price = mechanic_price
    rate.operator_price = operator_price

    if not keep_enabled_state:
        rate.is_enabled = is_enabled

    return False


async def main() -> None:
    created_rails = 0
    updated_rails = 0
    created_rates = 0
    updated_rates = 0

    async with SessionLocal() as session:
        machines = {
            machine.name: machine
            for machine in (
                await session.execute(select(Machine).where(Machine.is_active.is_(True)))
            ).scalars().all()
        }

        for item in rows():
            placeholder_pack = (
                item["pieces_per_pack"] == 1 and not item["rates_enabled"]
            )

            for base_name in item["bases"]:
                for rail_name in rail_names(
                    item["rail_class"],
                    item["shapes"],
                    base_name,
                ):
                    length = item["length"]

                    if " Напр " in rail_name:
                        length = rail_name.rsplit(" ", maxsplit=1)[1].removesuffix("м")

                    rail = (
                        await session.execute(select(Rail).where(Rail.name == rail_name))
                    ).scalar_one_or_none()

                    if rail is None:
                        rail = Rail(
                            name=rail_name,
                            length=Decimal(length),
                            pieces_per_pack=item["pieces_per_pack"],
                            metal=MetalType.ZINC,
                            is_active=True,
                        )
                        session.add(rail)
                        await session.flush()
                        created_rails += 1
                    else:
                        rail.length = Decimal(length)
                        if not placeholder_pack or rail.pieces_per_pack == 1:
                            rail.pieces_per_pack = item["pieces_per_pack"]
                        rail.is_active = True
                        updated_rails += 1

                    for machine_names, mechanic_raw, operator_raw in item["rates"]:
                        for machine_name in machine_names:
                            machine = machines.get(machine_name)

                            if machine is None:
                                raise RuntimeError(f"Machine not found: {machine_name}")

                            was_created = await upsert_rate(
                                session,
                                rail.id,
                                machine.id,
                                Decimal(mechanic_raw),
                                Decimal(operator_raw),
                                item["rates_enabled"],
                                keep_enabled_state=placeholder_pack,
                            )

                            if was_created:
                                created_rates += 1
                            else:
                                updated_rates += 1

        await session.commit()

    print(f"created_rails={created_rails}")
    print(f"updated_rails={updated_rails}")
    print(f"created_rates={created_rates}")
    print(f"updated_rates={updated_rates}")


if __name__ == "__main__":
    asyncio.run(main())
