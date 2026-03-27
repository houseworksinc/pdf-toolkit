"""Add cancelled status to enum

Revision ID: a3f1b7c9d2e4
Revises: cb241a02b314
Create Date: 2026-02-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a3f1b7c9d2e4'
down_revision: Union[str, None] = 'cb241a02b314'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'cancelled' value to status_enum
    op.execute("ALTER TYPE status_enum ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # For safety, we'll leave the enum value in place
    pass
