"""оценки и «н» из выгрузки электронного журнала преподавателя

Revision ID: a8b9c0d1e2f3
Revises: r1a2b3c4d5e6
Create Date: 2026-10-29 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a8b9c0d1e2f3'
down_revision = 'r1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'lesson_marks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subject_code', sa.String(length=32), nullable=False),
        sa.Column('subject_name', sa.String(length=255), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('grade', sa.Integer(), nullable=True),
        sa.Column('absent', sa.Boolean(), nullable=False),
        sa.Column('imported_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('student_id', 'subject_code', 'date', 'slot', name='uq_lesson_mark'),
    )
    op.create_index('ix_lesson_marks_student_id', 'lesson_marks', ['student_id'])
    op.create_index('ix_lesson_marks_date', 'lesson_marks', ['date'])
    op.create_table(
        'journal_lessons',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subject_code', sa.String(length=32), nullable=False),
        sa.Column('subject_name', sa.String(length=255), nullable=False),
        sa.Column('group_key', sa.String(length=255), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('homework', sa.String(length=500), nullable=True),
        sa.UniqueConstraint('subject_code', 'group_key', 'date', 'slot', name='uq_journal_lesson'),
    )
    op.create_index('ix_journal_lessons_subject_code', 'journal_lessons', ['subject_code'])
    op.create_index('ix_journal_lessons_date', 'journal_lessons', ['date'])


def downgrade() -> None:
    # Индексы уходят вместе с таблицами; удалять их отдельно MySQL не даёт, пока на них опирается внешний ключ.
    op.drop_table('journal_lessons')
    op.drop_table('lesson_marks')
