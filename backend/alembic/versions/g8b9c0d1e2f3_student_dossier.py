"""досье студента: профиль, представители, заметки, журнал просмотров

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-10-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'g8b9c0d1e2f3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'student_profiles',
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), primary_key=True),
        sa.Column('birth_date', sa.Date(), nullable=True),
        sa.Column('funding', sa.String(16), nullable=True),
        sa.Column('phone', sa.String(32), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('messenger', sa.String(128), nullable=True),
        sa.Column('registration_address', sa.String(512), nullable=True),
        sa.Column('residence_address', sa.String(512), nullable=True),
        sa.Column('special_enc', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'student_guardians',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('relation', sa.String(64), nullable=False),
        sa.Column('phone', sa.String(32), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_student_guardians_student_id', 'student_guardians', ['student_id'])
    op.create_table(
        'student_notes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_student_notes_student_id', 'student_notes', ['student_id'])
    op.create_table(
        'dossier_access_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('included_special', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_dossier_access_log_student_id', 'dossier_access_log', ['student_id'])
    op.create_index('ix_dossier_access_log_created_at', 'dossier_access_log', ['created_at'])


def downgrade() -> None:
    op.drop_table('dossier_access_log')
    op.drop_table('student_notes')
    op.drop_table('student_guardians')
    op.drop_table('student_profiles')
