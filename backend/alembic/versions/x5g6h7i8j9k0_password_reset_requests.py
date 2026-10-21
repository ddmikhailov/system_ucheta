"""password reset requests

Revision ID: x5g6h7i8j9k0
Revises: w4f5g6h7i8j9
Create Date: 2026-10-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'x5g6h7i8j9k0'
down_revision = 'w4f5g6h7i8j9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'password_reset_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('requested_ip', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index(
        'ix_password_reset_requests_user_status', 'password_reset_requests', ['user_id', 'status'],
    )


def downgrade() -> None:
    # Индекс уходит вместе с таблицей; отдельный drop_index на MySQL падает: он нужен внешнему ключу user_id.
    op.drop_table('password_reset_requests')
