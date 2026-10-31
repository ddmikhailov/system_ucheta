"""group_subjects: дисциплины группы и преподаватели

Revision ID: d1e2f3a4b5c6
Revises: r1a2b3c4d5e6
Create Date: 2026-10-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd1e2f3a4b5c6'
down_revision = 'r1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'group_subjects',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code', sa.String(32), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('teacher_name', sa.String(255), nullable=True),
        sa.Column('teacher_phone', sa.String(32), nullable=True),
        sa.Column('note', sa.String(500), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('study_group_id', 'code', name='uq_group_subject_code'),
    )
    op.create_index('ix_group_subjects_study_group_id', 'group_subjects', ['study_group_id'])


def downgrade() -> None:
    op.drop_index('ix_group_subjects_study_group_id', table_name='group_subjects')
    op.drop_table('group_subjects')
