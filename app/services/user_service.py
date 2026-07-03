from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User, UserRole


class UserService:
    async def get(self, user_id: int):
        async with SessionLocal() as session:
            return await session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int):
        async with SessionLocal() as session:
            result = await session.execute(
                select(User).where(
                    User.telegram_id == telegram_id
                )
            )

            return result.scalar_one_or_none()

    async def set_role(self, user_id: int, role: UserRole):
        async with SessionLocal() as session:
            user = await session.get(User, user_id)
            user.role = role

            await session.commit()
            await session.refresh(user)

            return user

    async def get_by_role(self, role: UserRole):
        async with SessionLocal() as session:
            result = await session.execute(
                select(User)
                .where(
                    User.role == role,
                    User.is_active.is_(True),
                )
                .order_by(User.full_name)
            )

            return result.scalars().all()

    async def get_mechanics(self):
        return await self.get_by_role(UserRole.MECHANIC)

    async def get_operators(self):
        return await self.get_by_role(UserRole.OPERATOR)

    async def get_admins(self):
        return await self.get_by_role(UserRole.ADMIN)

    async def create(
        self,
        telegram_id: int,
        full_name: str,
        role: UserRole,
        shift_number: int,
    ):
        async with SessionLocal() as session:
            user = User(
                telegram_id=telegram_id,
                full_name=full_name,
                role=role,
                shift_number=shift_number,
                is_active=True,
            )

            session.add(user)
            await session.commit()
            await session.refresh(user)

            return user


user_service = UserService()
