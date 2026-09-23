"""in-app notifications

Revision ID: c7a2e4f9d1b3
Revises: a3f6d1c9b0e2
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7a2e4f9d1b3'
down_revision = 'a3f6d1c9b0e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'in_app_notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('message', sa.String(length=500), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=True),
        sa.Column('entity_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'ix_in_app_notifications_user_id', 'in_app_notifications', ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_in_app_notifications_user_id', table_name='in_app_notifications')
    op.drop_table('in_app_notifications')
