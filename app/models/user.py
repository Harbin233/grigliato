from enum import Enum

from sqlalchemy import Boolean, Enum as SqlEnum, Integer, BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class UserRole(str, Enum):
    OPERATOR = "OPERATOR"
    MECHANIC = "MECHANIC"


class User(BaseModel):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole),
        nullable=False,
    )

    shift_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    work_sessions = relationship(
        "WorkSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
