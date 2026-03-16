"""consolidate_nmr_results_into_scalar_results

Revision ID: ebdffbdff6d0
Revises: 69f02f29e987
Create Date: 2025-06-24 10:25:37.259777

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ebdffbdff6d0'
down_revision: Union[str, None] = '69f02f29e987'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Data Migration - Copy ammonium_concentration_mm from nmr_results to scalar_results
    op.execute("""
        UPDATE scalar_results
        SET solution_ammonium_concentration = (
            SELECT nmr_results.ammonium_concentration_mm
            FROM nmr_results
            WHERE nmr_results.result_id = scalar_results.result_id
        )
        WHERE EXISTS (
            SELECT 1
            FROM nmr_results
            WHERE nmr_results.result_id = scalar_results.result_id
        )
    """)

    # Step 2: Schema Change - Drop the nmr_results table
    op.drop_table('nmr_results')


def downgrade() -> None:
    """Downgrade schema."""
    raise NotImplementedError("Downgrade from this migration is not supported as it involves data loss.")
