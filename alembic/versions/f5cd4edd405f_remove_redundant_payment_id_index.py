"""remove redundant payment id index

Revision ID: f5cd4edd405f
Revises: 7220ce4e703c
Create Date: 2026-11-28 21:06:57.871620

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5cd4edd405f'
down_revision: Union[str, Sequence[str], None] = '7220ce4e703c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the redundant non-unique payments.id index."""
    op.drop_index("ix_payments_id", table_name="payments")


def downgrade() -> None:
    """Restore the historical payments.id index."""
    op.create_index(
        "ix_payments_id",
        "payments",
        ["id"],
        unique=False,
    )
