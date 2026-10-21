"""группа риска по неуважительным пропускам; «Восполнить пропуски»: флаг кода отметки и закрытия куратором

Revision ID: z7c1m2p3n4s5
Revises: w4f5g6h7i8j9
Create Date: 2026-10-21 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'z7c1m2p3n4s5'
down_revision = 'w4f5g6h7i8j9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('mark_codes', sa.Column('no_compensation', sa.Boolean(), nullable=False, server_default=sa.false()))
    # Производственная практика и ИУП — отсутствие, но восполнять нечего (решение 21.10.2026).
    op.execute("UPDATE mark_codes SET no_compensation = 1 WHERE code IN ('р', 'и')")
    op.create_table(
        'absence_compensations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id', ondelete='CASCADE'), nullable=False),
        sa.Column('closed_on', sa.Date(), nullable=False),
        sa.Column('comment', sa.String(length=1000), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_absence_compensations_student_id', 'absence_compensations', ['student_id'])


def downgrade() -> None:
    op.drop_index('ix_absence_compensations_student_id', table_name='absence_compensations')
    op.drop_table('absence_compensations')
    op.drop_column('mark_codes', 'no_compensation')
