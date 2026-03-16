"""add missing icp element columns

Revision ID: 3d67080ef6f5
Revises: 58f273ca781f
Create Date: 2026-01-28 12:06:21.082474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d67080ef6f5'
down_revision: Union[str, None] = '58f273ca781f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = {col['name'] for col in inspector.get_columns('icp_results')}

    new_columns = {
        'sr': sa.Column('sr', sa.Float(), nullable=True),
        'y': sa.Column('y', sa.Float(), nullable=True),
        'nb': sa.Column('nb', sa.Float(), nullable=True),
        'sb': sa.Column('sb', sa.Float(), nullable=True),
        'cs': sa.Column('cs', sa.Float(), nullable=True),
        'ba': sa.Column('ba', sa.Float(), nullable=True),
        'nd': sa.Column('nd', sa.Float(), nullable=True),
        'gd': sa.Column('gd', sa.Float(), nullable=True),
        'pt': sa.Column('pt', sa.Float(), nullable=True),
        'rh': sa.Column('rh', sa.Float(), nullable=True),
        'ir': sa.Column('ir', sa.Float(), nullable=True),
        'pd': sa.Column('pd', sa.Float(), nullable=True),
        'ru': sa.Column('ru', sa.Float(), nullable=True),
        'os': sa.Column('os', sa.Float(), nullable=True),
        'tl': sa.Column('tl', sa.Float(), nullable=True),
    }

    for name, column in new_columns.items():
        if name not in columns:
            op.add_column('icp_results', column)


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = {col['name'] for col in inspector.get_columns('icp_results')}

    drop_order = [
        'tl', 'os', 'ru', 'pd', 'ir', 'rh', 'pt', 'gd',
        'nd', 'ba', 'cs', 'sb', 'nb', 'y', 'sr',
    ]

    for name in drop_order:
        if name in columns:
            op.drop_column('icp_results', name)
