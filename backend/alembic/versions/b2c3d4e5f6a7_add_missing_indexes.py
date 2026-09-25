"""add missing indexes: audit_log.created_at, attendance_marks.date, in_app_notifications(user_id, read_at) (see TODO.md 5)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-25 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _existing_index_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "ix_audit_log_created_at" not in _existing_index_names(inspector, "audit_log"):
        op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    if "ix_attendance_marks_date" not in _existing_index_names(inspector, "attendance_marks"):
        op.create_index("ix_attendance_marks_date", "attendance_marks", ["date"])

    if "ix_in_app_notifications_user_read" not in _existing_index_names(inspector, "in_app_notifications"):
        op.create_index(
            "ix_in_app_notifications_user_read", "in_app_notifications", ["user_id", "read_at"]
        )


def downgrade() -> None:
    op.drop_index("ix_in_app_notifications_user_read", table_name="in_app_notifications")
    op.drop_index("ix_attendance_marks_date", table_name="attendance_marks")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
