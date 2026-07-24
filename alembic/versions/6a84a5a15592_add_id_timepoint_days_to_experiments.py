"""add id_timepoint_days to experiments

Issue #81: day value parsed from the '-t<days>' experiment ID token.
Additive, single model, reversible. No view changes.

Revision ID: 6a84a5a15592
Revises: 98b849b9f08b
Create Date: 2026-07-24 15:06:52.884133

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a84a5a15592'
down_revision: Union[str, None] = '98b849b9f08b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('experiments', sa.Column('id_timepoint_days', sa.Float(), nullable=True))
    op.create_index(op.f('ix_experiments_id_timepoint_days'), 'experiments', ['id_timepoint_days'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_experiments_id_timepoint_days'), table_name='experiments')
    op.drop_column('experiments', 'id_timepoint_days')
