"""правка прошлых сданных дней куратором — через проверку зав. отделением (интерфейс 3.2)

Revision ID: u2d3e4f5g6h7
Revises: t1c2d3e4f5g6
Create Date: 2026-10-06 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'u2d3e4f5g6h7'
down_revision = 't1c2d3e4f5g6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'attendance_change_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('requested_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('exceptions_json', sa.Text(), nullable=False),
        sa.Column('first_period', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('reviewed_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('review_comment', sa.String(length=500), nullable=True),
    )
    op.create_index('ix_attendance_change_requests_study_group_id', 'attendance_change_requests', ['study_group_id'])
    op.create_index('ix_attendance_change_requests_status', 'attendance_change_requests', ['status'])


def downgrade() -> None:
    op.drop_index('ix_attendance_change_requests_status', table_name='attendance_change_requests')
    op.drop_index('ix_attendance_change_requests_study_group_id', table_name='attendance_change_requests')
    op.drop_table('attendance_change_requests')
