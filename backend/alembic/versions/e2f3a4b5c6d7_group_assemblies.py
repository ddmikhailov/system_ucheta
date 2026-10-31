"""общие собрания группы: протокол п. 5.1.10 положения о кураторе («Папка куратора»)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-10-29 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'group_assemblies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('school_year', sa.String(length=9), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('assembly_date', sa.Date(), nullable=True),
        sa.Column('chair', sa.String(length=255), nullable=True),
        sa.Column('secretary', sa.String(length=255), nullable=True),
        sa.Column('present_count', sa.Integer(), nullable=True),
        sa.Column('agenda', sa.Text(), nullable=True),
        sa.Column('listened', sa.Text(), nullable=True),
        sa.Column('resolved', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_group_assemblies_study_group_id', 'group_assemblies', ['study_group_id'])
    op.create_index('ix_group_assemblies_school_year', 'group_assemblies', ['school_year'])


def downgrade() -> None:
    op.drop_index('ix_group_assemblies_school_year', table_name='group_assemblies')
    op.drop_index('ix_group_assemblies_study_group_id', table_name='group_assemblies')
    op.drop_table('group_assemblies')
