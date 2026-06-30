"""add overtime flags

Revision ID: c74c1f6c1d1a
Revises: b1f4e3a9d2c0
Create Date: 2026-06-30 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c74c1f6c1d1a"
down_revision: Union[str, Sequence[str], None] = "b1f4e3a9d2c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shift_mechanics",
        sa.Column(
            "is_overtime",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "work_sessions",
        sa.Column(
            "is_overtime",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.alter_column("shift_mechanics", "is_overtime", server_default=None)
    op.alter_column("work_sessions", "is_overtime", server_default=None)


def downgrade() -> None:
    op.drop_column("work_sessions", "is_overtime")
    op.drop_column("shift_mechanics", "is_overtime")
