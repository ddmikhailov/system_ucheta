import datetime

from sqlalchemy import Date, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AssignmentRole, StudentStatus


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False)
    status: Mapped[StudentStatus] = mapped_column(
        Enum(StudentStatus), default=StudentStatus.STUDYING, nullable=False
    )
    enrolled_at: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    left_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    study_group: Mapped["StudyGroup"] = relationship(back_populates="students")

    @property
    def full_name(self) -> str:
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(p for p in parts if p)


class CuratorAssignment(Base):
    """Кто ведёт группу и с какой по какую дату — с историей замен."""

    __tablename__ = "curator_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role_type: Mapped[AssignmentRole] = mapped_column(Enum(AssignmentRole), nullable=False)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    study_group: Mapped["StudyGroup"] = relationship(back_populates="curator_assignments")
    user: Mapped["User"] = relationship(back_populates="curator_assignments")

    def is_active_on(self, day: datetime.date) -> bool:
        if self.start_date > day:
            return False
        if self.end_date is not None and self.end_date < day:
            return False
        return True
