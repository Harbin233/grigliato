"""add roll weight to shift machine assignments

Revision ID: a4d2b9e1c705
Revises: e6d8c0a91b42
Create Date: 2026-07-04 00:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4d2b9e1c705"
down_revision: Union[str, Sequence[str], None] = "e6d8c0a91b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shift_machine_assignments",
        sa.Column("roll_weight_kg", sa.Numeric(8, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shift_machine_assignments", "roll_weight_kg")
