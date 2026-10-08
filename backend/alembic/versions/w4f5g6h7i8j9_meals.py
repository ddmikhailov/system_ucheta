"""питание: выбор по студентам, недельная подача, правки по дням, финансирование группы, вид задачи

Revision ID: w4f5g6h7i8j9
Revises: v3e4f5g6h7i8
Create Date: 2026-10-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'w4f5g6h7i8j9'
down_revision = 'v3e4f5g6h7i8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('study_groups', sa.Column('funding', sa.String(length=16), nullable=True))
    op.add_column('tasks', sa.Column('kind', sa.String(length=16), nullable=True))
    op.create_table(
        'student_meals',
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('eats', sa.Boolean(), nullable=False),
        sa.Column('updated_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'meal_submissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('submitted_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('study_group_id', 'week_start', name='uq_meal_submission_week'),
    )
    op.create_index('ix_meal_submissions_study_group_id', 'meal_submissions', ['study_group_id'])
    op.create_table(
        'meal_day_overrides',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('edited_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('edited_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('study_group_id', 'date', name='uq_meal_override_day'),
    )
    op.create_index('ix_meal_day_overrides_study_group_id', 'meal_day_overrides', ['study_group_id'])


def downgrade() -> None:
    op.drop_index('ix_meal_day_overrides_study_group_id', table_name='meal_day_overrides')
    op.drop_table('meal_day_overrides')
    op.drop_index('ix_meal_submissions_study_group_id', table_name='meal_submissions')
    op.drop_table('meal_submissions')
    op.drop_table('student_meals')
    op.drop_column('tasks', 'kind')
    op.drop_column('study_groups', 'funding')
