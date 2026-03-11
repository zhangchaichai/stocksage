"""Add strategy_id column to screener_jobs for predefined strategy support

Revision ID: 002_screener_strat
Revises: 001_enhanced_bt
Create Date: 2026-03-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_screener_strat'
down_revision: Union[str, None] = '001_enhanced_bt'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('screener_jobs', sa.Column('strategy_id', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('screener_jobs', 'strategy_id')
