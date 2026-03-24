"""add ferrous iron yield columns

Revision ID: c095022cadbd
Revises: f59050b45fc4
Create Date: 2026-03-24 14:30:27.120966

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# revision identifiers, used by Alembic.
revision: str = 'c095022cadbd'
down_revision: Union[str, None] = 'f59050b45fc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('experimental_conditions', sa.Column('total_ferrous_iron', sa.Float(), nullable=True))
    op.add_column('scalar_results', sa.Column('ferrous_iron_yield_h2_pct', sa.Float(), nullable=True))
    op.add_column('scalar_results', sa.Column('ferrous_iron_yield_nh3_pct', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scalar_results', 'ferrous_iron_yield_nh3_pct')
    op.drop_column('scalar_results', 'ferrous_iron_yield_h2_pct')
    op.drop_column('experimental_conditions', 'total_ferrous_iron')
