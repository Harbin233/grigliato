from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class ShiftMachineAssignment(BaseModel):
    __tablename__ = "shift_machine_assignments"

    __table_args__ = (
        UniqueConstraint(
            "shift_id",
            "machine_id",
            name="uq_shift_machine_assignment",
        ),
    )

    shift_id: Mapped[int] = mapped_column(
        ForeignKey("shifts.id"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id"),
        nullable=False,
    )

    shift = relationship("Shift")
    user = relationship("User")
    machine = relationship("Machine")
