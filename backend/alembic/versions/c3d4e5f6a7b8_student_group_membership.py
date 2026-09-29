"""student_group_memberships — history of group membership (see TODO.md 3:
transferring a student to another group used to rewrite their whole
attendance history under the new group)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "student_group_memberships" not in inspector.get_table_names():
        op.create_table(
            "student_group_memberships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
            sa.Column("study_group_id", sa.Integer(), sa.ForeignKey("study_groups.id"), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=True),
        )
        op.create_index(
            "ix_student_group_memberships_student", "student_group_memberships", ["student_id"]
        )
        op.create_index(
            "ix_student_group_memberships_group", "student_group_memberships", ["study_group_id"]
        )

    # Бэкафилл: у каждого уже существующего студента — одна открытая запись
    # членства в его текущей группе с даты зачисления. Только если у него
    # ещё нет ни одной записи (повторный запуск после обрыва деплоя не
    # должен плодить дубли).
    existing_student_ids = {
        row[0]
        for row in bind.execute(sa.text("SELECT DISTINCT student_id FROM student_group_memberships"))
    }
    students = bind.execute(sa.text("SELECT id, study_group_id, enrolled_at FROM students")).fetchall()
    for student_id, study_group_id, enrolled_at in students:
        if student_id in existing_student_ids:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO student_group_memberships (student_id, study_group_id, start_date, end_date) "
                "VALUES (:student_id, :study_group_id, :start_date, NULL)"
            ),
            {"student_id": student_id, "study_group_id": study_group_id, "start_date": enrolled_at},
        )


def downgrade() -> None:
    op.drop_table("student_group_memberships")
