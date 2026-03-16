"""add_ammonia_quantification_method

Revision ID: 9d7f16845bc8
Revises: ad0838aca6b9
Create Date: 2025-07-11 16:50:05.326830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d7f16845bc8'
down_revision: Union[str, None] = 'ad0838aca6b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema and migrate data."""
    op.add_column('scalar_results', sa.Column('ammonium_quant_method', sa.String(), nullable=True))
    
    # Data migration: back-populate existing rows to 'NMR'
    op.execute("UPDATE scalar_results SET ammonium_quant_method = 'NMR' WHERE ammonium_quant_method IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scalar_results', 'ammonium_quant_method')
