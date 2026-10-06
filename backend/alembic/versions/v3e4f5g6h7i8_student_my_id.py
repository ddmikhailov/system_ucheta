"""вкладка «Мой ID»: биометрия и чаты MAX по студентам

Revision ID: v3e4f5g6h7i8
Revises: u2d3e4f5g6h7
Create Date: 2026-10-06 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'v3e4f5g6h7i8'
down_revision = 'u2d3e4f5g6h7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'student_my_id',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id', ondelete='CASCADE'), nullable=False),
        sa.Column('school_year', sa.String(length=9), nullable=False),
        sa.Column('biometrics', sa.Boolean(), nullable=True),
        sa.Column('biometrics_reason', sa.String(length=255), nullable=True),
        sa.Column('max_student', sa.Boolean(), nullable=True),
        sa.Column('max_student_reason', sa.String(length=255), nullable=True),
        sa.Column('max_parent', sa.Boolean(), nullable=True),
        sa.Column('max_parent_reason', sa.String(length=255), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('student_id', 'school_year', name='uq_student_my_id'),
    )
    op.create_index('ix_student_my_id_student_id', 'student_my_id', ['student_id'])


def downgrade() -> None:
    op.drop_index('ix_student_my_id_student_id', table_name='student_my_id')
    op.drop_table('student_my_id')
