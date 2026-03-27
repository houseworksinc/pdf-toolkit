"""Add CONVERT job type to enum

Revision ID: cb241a02b314
Revises: 
Create Date: 2025-12-29 13:56:58.613260

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'cb241a02b314'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'convert' value to job_type_enum
    op.execute("ALTER TYPE job_type_enum ADD VALUE IF NOT EXISTS 'convert'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # Removing enum values requires recreating the enum or leaving it
    # For safety, we'll leave the enum value in place
    pass
