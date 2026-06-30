from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class ProductionEntry(BaseModel):
    __tablename__ = "production_entries"

    shift_id: Mapped[int] = mapped_column(
        ForeignKey("shifts.id"),
        nullable=False,
    )

    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id"),
        nullable=False,
    )

    rail_id: Mapped[int] = mapped_column(
        ForeignKey("rails.id"),
        nullable=False,
    )

    operator_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    packs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    pieces: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    meters: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    operator_price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    mechanic_price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    operator_total: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    mechanic_total: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    rail_length: Mapped[float] = mapped_column(
        Numeric(6, 3),
        nullable=False,
    )

    pieces_per_pack: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
