from enum import Enum

from sqlalchemy import Enum as SqlEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class MechanicType(str, Enum):
    MAIN = "main"
    ASSISTANT = "assistant"


class ShiftMechanic(BaseModel):
    __tablename__ = "shift_mechanics"

    shift_id: Mapped[int] = mapped_column(
        ForeignKey("shifts.id"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    mechanic_type: Mapped[MechanicType] = mapped_column(
        SqlEnum(MechanicType),
        nullable=False,
    )
