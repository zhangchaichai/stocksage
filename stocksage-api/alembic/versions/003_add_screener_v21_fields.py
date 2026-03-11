"""Add top_n, enable_ai_score, candidates to screener_jobs for v2.1 three-layer architecture.

Revision ID: 003_screener_v21
Revises: 002_screener_strat
Create Date: 2026-03-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003_screener_v21'
down_revision: Union[str, None] = '002_screener_strat'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('screener_jobs', sa.Column('top_n', sa.Integer(), nullable=True, server_default='20'))
    op.add_column('screener_jobs', sa.Column('enable_ai_score', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('screener_jobs', sa.Column('candidates', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('screener_jobs', 'candidates')
    op.drop_column('screener_jobs', 'enable_ai_score')
    op.drop_column('screener_jobs', 'top_n')
