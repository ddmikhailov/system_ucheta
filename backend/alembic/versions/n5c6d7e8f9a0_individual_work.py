"""журнал индивидуальной работы: дата события и «вернуться к вопросу» в заметках досье

Revision ID: n5c6d7e8f9a0
Revises: m4b5c6d7e8f9
Create Date: 2026-10-05 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'n5c6d7e8f9a0'
down_revision = 'm4b5c6d7e8f9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('student_notes', sa.Column('occurred_on', sa.Date(), nullable=True))
    op.add_column('student_notes', sa.Column('follow_up_on', sa.Date(), nullable=True))
    op.add_column('student_notes', sa.Column('follow_up_done', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('student_notes', 'follow_up_done')
    op.drop_column('student_notes', 'follow_up_on')
    op.drop_column('student_notes', 'occurred_on')
