from sqlalchemy import func, select

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

    async def find_name_matches(
        self,
        full_name: str,
        *,
        exclude_user_id: int | None = None,
        limit: int = 5,
    ):
        tokens = {
            token
            for token in full_name.lower().replace("ё", "е").split()
            if len(token) > 1
        }

        if not tokens:
            return []

        async with SessionLocal() as session:
            result = await session.execute(
                select(User)
                .where(User.is_active.is_(True))
                .order_by(User.full_name)
            )
            users = result.scalars().all()

        matches = []

        for user in users:
            if exclude_user_id is not None and user.id == exclude_user_id:
                continue

            user_tokens = {
                token
                for token in user.full_name.lower().replace("ё", "е").split()
                if len(token) > 1
            }
            score = len(tokens & user_tokens)

            if score:
                matches.append((score, user))

        matches.sort(
            key=lambda item: (-item[0], item[1].full_name)
        )

        return [user for _, user in matches[:limit]]

    async def create_manual_operator(
        self,
        full_name: str,
        shift_number: int,
    ):
        async with SessionLocal() as session:
            min_manual_id = await session.scalar(
                select(func.min(User.telegram_id)).where(
                    User.telegram_id < 0
                )
            )
            telegram_id = (min_manual_id or 0) - 1
            user = User(
                telegram_id=telegram_id,
                full_name=full_name,
                role=UserRole.OPERATOR,
                shift_number=shift_number,
                is_active=True,
            )

            session.add(user)
            await session.commit()
            await session.refresh(user)

            return user

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
