"""Add analyst_reports column to screener_jobs for AI analyst team reports.

Revision ID: 004_analyst_reports
Revises: 003_screener_v21
Create Date: 2026-03-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004_analyst_reports'
down_revision: Union[str, None] = '003_screener_v21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('screener_jobs', sa.Column('analyst_reports', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('screener_jobs', 'analyst_reports')
