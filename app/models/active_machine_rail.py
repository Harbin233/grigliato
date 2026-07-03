from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class ActiveMachineRail(BaseModel):
    __tablename__ = "active_machine_rails"

    __table_args__ = (
        UniqueConstraint(
            "shift_id",
            "machine_id",
            name="uq_active_machine_rail",
        ),
    )

    shift_id: Mapped[int] = mapped_column(
        ForeignKey("shifts.id"),
        nullable=False,
    )

    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id"),
        nullable=False,
    )

    machine_rail_id: Mapped[int] = mapped_column(
        ForeignKey("machine_rails.id"),
        nullable=False,
    )

    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    shift = relationship("Shift")
    machine = relationship("Machine")
    machine_rail = relationship("MachineRail")
    created_by = relationship("User")
