from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SqlEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class ShiftType(str, Enum):
    DAY = "day"
    NIGHT = "night"


class Shift(BaseModel):
    __tablename__ = "shifts"

    work_date: Mapped[Date] = mapped_column(
        Date,
        nullable=False,
    )

    shift_number: Mapped[int] = mapped_column(
        nullable=False,
    )

    shift_type: Mapped[ShiftType] = mapped_column(
        SqlEnum(ShiftType),
        nullable=False,
    )

    started_at: Mapped[DateTime] = mapped_column(
        DateTime,
        nullable=False,
    )

    ended_at: Mapped[DateTime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    started_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    started_by = relationship(
        "User",
    )

    work_sessions = relationship(
        "WorkSession",
        back_populates="shift",
        cascade="all, delete-orphan",
    )
