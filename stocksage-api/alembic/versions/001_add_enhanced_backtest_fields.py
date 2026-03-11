"""Add enhanced backtest fields (Sharpe, Sortino, VaR, Wyckoff, dealer signals)

Revision ID: 001_enhanced_bt
Revises: None
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001_enhanced_bt'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('backtest_results', sa.Column('sharpe_ratio', sa.Float, nullable=True))
    op.add_column('backtest_results', sa.Column('sortino_ratio', sa.Float, nullable=True))
    op.add_column('backtest_results', sa.Column('var_95', sa.Float, nullable=True))
    op.add_column('backtest_results', sa.Column('wyckoff_phase_at_action', sa.String(32), nullable=True))
    op.add_column('backtest_results', sa.Column('dealer_signals_at_action', sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column('backtest_results', 'dealer_signals_at_action')
    op.drop_column('backtest_results', 'wyckoff_phase_at_action')
    op.drop_column('backtest_results', 'var_95')
    op.drop_column('backtest_results', 'sortino_ratio')
    op.drop_column('backtest_results', 'sharpe_ratio')
