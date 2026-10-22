"""запросы куратора на полное удаление студента

Revision ID: z9k0l1m2n3o4
Revises: y6h7i8j9k0l1
Create Date: 2026-10-21 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'z9k0l1m2n3o4'
down_revision = 'y6h7i8j9k0l1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'student_deletion_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('requested_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('reviewed_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('review_comment', sa.String(length=500), nullable=True),
    )
    op.create_index('ix_student_deletion_requests_student_id', 'student_deletion_requests', ['student_id'])
    op.create_index('ix_student_deletion_requests_status', 'student_deletion_requests', ['status'])


def downgrade() -> None:
    op.drop_table('student_deletion_requests')
