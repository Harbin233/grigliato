from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Machine(BaseModel):
    __tablename__ = "machines"

    name: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
    )

    machine_type: Mapped[str] = mapped_column(
        String(30),
        default="grigliato",
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )

    rails = relationship(
        "MachineRail",
        back_populates="machine",
        cascade="all, delete-orphan",
    )

    work_sessions = relationship(
        "WorkSession",
        back_populates="machine",
        cascade="all, delete-orphan",
    )
