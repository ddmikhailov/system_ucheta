"""отчёт куратора за семестр: ручные показатели (этап 8)

Revision ID: t1c2d3e4f5g6
Revises: s0b1c2d3e4f5
Create Date: 2026-10-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 't1c2d3e4f5g6'
down_revision = 's0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'curator_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('school_year', sa.String(length=9), nullable=False),
        sa.Column('semester', sa.Integer(), nullable=False),
        sa.Column('values_json', sa.Text(), nullable=False),
        sa.Column('updated_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('study_group_id', 'school_year', 'semester', name='uq_curator_report'),
    )
    op.create_index('ix_curator_reports_study_group_id', 'curator_reports', ['study_group_id'])


def downgrade() -> None:
    op.drop_index('ix_curator_reports_study_group_id', table_name='curator_reports')
    op.drop_table('curator_reports')
