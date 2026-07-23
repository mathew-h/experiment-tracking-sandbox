"""add replicate_label to experiments

Revision ID: fe48608cabb7
Revises: ca5d57c6b272
Create Date: 2026-07-23 11:23:05.473082

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe48608cabb7'
down_revision: Union[str, None] = 'ca5d57c6b272'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('experiments', sa.Column('replicate_label', sa.String(), nullable=True))
    op.create_index(op.f('ix_experiments_replicate_label'), 'experiments', ['replicate_label'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_experiments_replicate_label'), table_name='experiments')
    op.drop_column('experiments', 'replicate_label')
