"""практика группы: периоды, база, руководители, получение характеристики; связь периодов отсутствия с практикой

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-10-29 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f3a4b5c6d7e8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'group_practices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('study_group_id', sa.Integer(), sa.ForeignKey('study_groups.id'), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('date_from', sa.Date(), nullable=False),
        sa.Column('date_to', sa.Date(), nullable=False),
        sa.Column('base', sa.String(length=255), nullable=True),
        sa.Column('college_supervisor', sa.String(length=255), nullable=True),
        sa.Column('base_supervisor', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=64), nullable=True),
        sa.Column('review_received', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('review_received_on', sa.Date(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_group_practices_study_group_id', 'group_practices', ['study_group_id'])
    with op.batch_alter_table('absence_periods') as batch:
        batch.add_column(sa.Column('group_practice_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_absence_periods_group_practice', 'group_practices', ['group_practice_id'], ['id'], ondelete='CASCADE')
        batch.create_index('ix_absence_periods_group_practice_id', ['group_practice_id'])


def downgrade() -> None:
    with op.batch_alter_table('absence_periods') as batch:
        batch.drop_index('ix_absence_periods_group_practice_id')
        batch.drop_constraint('fk_absence_periods_group_practice', type_='foreignkey')
        batch.drop_column('group_practice_id')
    op.drop_index('ix_group_practices_study_group_id', table_name='group_practices')
    op.drop_table('group_practices')
