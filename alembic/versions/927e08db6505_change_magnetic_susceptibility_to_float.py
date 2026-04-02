"""change magnetic_susceptibility to float

Revision ID: 927e08db6505
Revises: db40dd1e6422
Create Date: 2026-04-02 15:18:44.003017

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '927e08db6505'
down_revision: Union[str, None] = 'db40dd1e6422'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_VIEW_SAMPLE_CHARACTERIZATION = """
    CREATE VIEW v_sample_characterization AS
    SELECT
        ea.sample_id,
        ea.id          AS external_analysis_id,
        ea.analysis_type,
        ea.analysis_date,
        ea.laboratory,
        ea.analyst,
        ea.description,
        ea.magnetic_susceptibility,
        ea.pxrf_reading_no
    FROM external_analyses ea
    WHERE ea.sample_id IS NOT NULL
"""


def upgrade() -> None:
    """Upgrade schema."""
    # Drop view that depends on magnetic_susceptibility before altering the column type.
    op.execute("DROP VIEW IF EXISTS v_sample_characterization")

    op.alter_column(
        'external_analyses',
        'magnetic_susceptibility',
        existing_type=sa.VARCHAR(),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using='magnetic_susceptibility::double precision',
    )

    # Recreate the view now that the column is Float.
    op.execute(_VIEW_SAMPLE_CHARACTERIZATION)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_sample_characterization")

    op.alter_column(
        'external_analyses',
        'magnetic_susceptibility',
        existing_type=sa.Float(),
        type_=sa.VARCHAR(),
        existing_nullable=True,
    )

    op.execute(_VIEW_SAMPLE_CHARACTERIZATION)
