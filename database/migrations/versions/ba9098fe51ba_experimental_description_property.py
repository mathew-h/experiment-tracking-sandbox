"""Experimental description property - SQLite compatible

NOTE: The description property is implemented as a Python @property in the Experiment model.
It does not require any database schema changes. It uses the existing ExperimentNotes
relationship where the first note serves as the description.

All auto-generated changes have been REMOVED because they violate SQLite compatibility:
- ALTER COLUMN not supported (enum conversions, nullability changes)
- Self-referential FK causes CircularDependencyError
- Changes are unrelated to the description property feature

Revision ID: ba9098fe51ba
Revises: 2a832c8d5048
Create Date: 2025-10-27 12:12:49.731648
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ba9098fe51ba'
down_revision: Union[str, None] = '2a832c8d5048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent.
    
    No schema changes needed:
    - The description property is implemented purely in Python
    - It uses the existing experiment_notes table and relationship
    - No new columns or constraints are required
    
    All auto-generated changes removed because:
    1. ALTER COLUMN not supported in SQLite (lines 24-44 of original)
    2. Self-referential FK causes CircularDependencyError (line 45 of original)
    3. Unnamed constraints cannot be dropped later (line 45, 52 of original)
    4. Changes unrelated to description property feature
    """
    # No schema changes required for description property
    pass


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent.
    
    No changes to revert since no schema changes were made.
    """
    pass
