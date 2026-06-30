from sqlalchemy import Boolean, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class MachineRail(BaseModel):
    __tablename__ = "machine_rails"

    __table_args__ = (
        UniqueConstraint(
            "machine_id",
            "rail_id",
            name="uq_machine_rail",
        ),
    )

    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id"),
        nullable=False,
    )

    rail_id: Mapped[int] = mapped_column(
        ForeignKey("rails.id"),
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

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    machine = relationship(
        "Machine",
        back_populates="rails",
    )

    rail = relationship(
        "Rail",
        back_populates="machines",
    )
