"""clamp negative icp ppm to zero

Revision ID: 458f344f73d8
Revises: 4e8b99151ab0
Create Date: 2026-03-30 15:35:34.565158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '458f344f73d8'
down_revision: Union[str, None] = '4e8b99151ab0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# All 27 fixed ICP element columns in icp_results (ppm, must be >= 0)
_ICP_ELEMENT_COLUMNS = [
    'fe', 'si', 'ni', 'cu', 'mo', 'zn', 'mn', 'ca', 'cr', 'co', 'mg', 'al',
    'sr', 'y', 'nb', 'sb', 'cs', 'ba', 'nd', 'gd', 'pt', 'rh', 'ir',
    'pd', 'ru', 'os', 'tl',
]


def upgrade() -> None:
    """Set any negative ICP element ppm values to 0. NULLs are left untouched."""
    for col in _ICP_ELEMENT_COLUMNS:
        op.execute(
            f'UPDATE icp_results SET "{col}" = 0 WHERE "{col}" < 0'
        )


def downgrade() -> None:
    # Original negative values are not recoverable after this migration.
    # Downgrade is intentionally a no-op.
    pass
