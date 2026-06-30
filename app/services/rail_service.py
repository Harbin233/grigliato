from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.rail import Rail


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


rail_service = RailService()
