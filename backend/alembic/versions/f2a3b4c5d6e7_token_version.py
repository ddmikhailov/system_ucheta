"""user token_version for session revocation

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "token_version" not in columns:
        op.add_column(
            'users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0')
        )
        op.alter_column('users', 'token_version', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'token_version')
