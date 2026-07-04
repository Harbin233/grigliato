"""add mechanic operator role

Revision ID: f2b7a61d9c02
Revises: a4d2b9e1c705
Create Date: 2026-07-04 04:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f2b7a61d9c02"
down_revision: Union[str, Sequence[str], None] = "a4d2b9e1c705"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'MECHANIC_OPERATOR'")


def downgrade() -> None:
    pass
