from enum import Enum

from sqlalchemy import Boolean, Enum as SqlEnum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class MetalType(str, Enum):
    ALUMINUM = "aluminum"
    ZINC = "zinc"


class Rail(BaseModel):
    __tablename__ = "rails"

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    length: Mapped[float] = mapped_column(
        Numeric(6, 3),
        nullable=False,
    )

    pieces_per_pack: Mapped[int] = mapped_column(
        nullable=False,
    )

    metal: Mapped[MetalType] = mapped_column(
        SqlEnum(MetalType),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    machines = relationship(
        "MachineRail",
        back_populates="rail",
        cascade="all, delete-orphan",
    )
