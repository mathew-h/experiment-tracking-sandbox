"""fixing_mag_susc

Revision ID: 1059508a9806
Revises: 39fa8cb5c06a
Create Date: 2025-06-12 16:25:33.966896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '1059508a9806'
down_revision: Union[str, None] = '39fa8cb5c06a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # First check if column exists and drop it if it does
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('external_analyses')]
    
    if 'magnetic_susceptibility' in columns:
        op.drop_column('external_analyses', 'magnetic_susceptibility')
    
    # Now add the column fresh
    op.add_column('external_analyses', sa.Column('magnetic_susceptibility', sa.String(), nullable=True))
    
    # Migrate existing data from description field
    external_analyses = connection.execute(
        text("SELECT id, description FROM external_analyses WHERE analysis_type = 'Magnetic Susceptibility'")
    ).fetchall()
    
    for analysis in external_analyses:
        if analysis.description:
            # Extract value from description string (e.g., "Magnetic susceptibility: 0.5 (1x10^-3)")
            import re
            match = re.search(r'Magnetic susceptibility:\s*([\d.-]+)\s*\(', analysis.description)
            if match:
                value = match.group(1)
                connection.execute(
                    text("UPDATE external_analyses SET magnetic_susceptibility = :value WHERE id = :id"),
                    {"value": value, "id": analysis.id}
                )

def downgrade():
    # Migrate data back to description field
    connection = op.get_bind()
    analyses = connection.execute(
        text("SELECT id, magnetic_susceptibility FROM external_analyses WHERE magnetic_susceptibility IS NOT NULL")
    ).fetchall()
    
    for analysis in analyses:
        if analysis.magnetic_susceptibility is not None:
            description = f"Magnetic susceptibility: {analysis.magnetic_susceptibility} (1x10^-3)"
            connection.execute(
                text("UPDATE external_analyses SET description = :desc WHERE id = :id"),
                {"desc": description, "id": analysis.id}
            )
    
    # Remove column
    op.drop_column('external_analyses', 'magnetic_susceptibility')