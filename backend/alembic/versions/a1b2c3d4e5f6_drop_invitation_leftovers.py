"""drop invitations table and attendance_marks.basis_deadline (dead code, see TODO.md 5)

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-09-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "invitations" in inspector.get_table_names():
        op.drop_table('invitations')

    mark_columns = {c["name"] for c in inspector.get_columns("attendance_marks")}
    if "basis_deadline" in mark_columns:
        op.drop_column('attendance_marks', 'basis_deadline')


def downgrade() -> None:
    op.add_column('attendance_marks', sa.Column('basis_deadline', sa.Date(), nullable=True))
    op.create_table(
        'invitations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token', sa.String(length=64), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('issued_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
