"""Add date_from, date_to, market_filters columns to screener_jobs.

Revision ID: 005_screener_date_market
Revises: 004_analyst_reports
Create Date: 2026-03-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '005_screener_date_market'
down_revision: Union[str, None] = '004_analyst_reports'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('screener_jobs', sa.Column('date_from', sa.String(16), nullable=True))
    op.add_column('screener_jobs', sa.Column('date_to', sa.String(16), nullable=True))
    op.add_column('screener_jobs', sa.Column('market_filters', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('screener_jobs', 'market_filters')
    op.drop_column('screener_jobs', 'date_to')
    op.drop_column('screener_jobs', 'date_from')
