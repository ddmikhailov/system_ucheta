from app.models.audit import AuditLog
from app.models.auth import Role, User
from app.models.calendar import AcademicCalendarDay, GroupCalendarOverride
from app.models.events import CuratorReport, GroupEvent, GroupEventAttendee, ParentMeeting, ParentMeetingAttendee
from app.models.dossier import DossierAccessLog, StudentGuardian, StudentNote, StudentProfile
from app.models.enums import (
    AssignmentRole,
    BasisStatus,
    DayType,
    MarkSource,
    RoleCode,
    StudentStatus,
)
from app.models.marks import AbsenceCompensation, AbsencePeriod, AttendanceChangeRequest, AttendanceMark, DaySubmission, MarkCode
from app.models.notifications import InAppNotification
from app.models.password_reset import PasswordResetRequest
from app.models.tasks import Task, TaskAssignment, TaskComment, TaskRow, TaskTemplate
from app.models.meals import MealDayOverride, MealSubmission, StudentMeal
from app.models.my_id import StudentMyId
from app.models.org import Department, StudyGroup
from app.models.student_deletion import StudentDeletionRequest
from app.models.urgent_report import UrgentReport
from app.models.people import CuratorAssignment, Student, StudentGroupMembership

__all__ = [
    "AbsenceCompensation",
    "AbsencePeriod",
    "AcademicCalendarDay",
    "AssignmentRole",
    "AttendanceChangeRequest",
    "AttendanceMark",
    "AuditLog",
    "BasisStatus",
    "CuratorAssignment",
    "CuratorReport",
    "DaySubmission",
    "DayType",
    "Department",
    "DossierAccessLog",
    "GroupCalendarOverride",
    "GroupEvent",
    "GroupEventAttendee",
    "InAppNotification",
    "PasswordResetRequest",
    "MarkCode",
    "MarkSource",
    "ParentMeeting",
    "ParentMeetingAttendee",
    "Role",
    "RoleCode",
    "Student",
    "StudentGuardian",
    "MealDayOverride",
    "MealSubmission",
    "StudentMeal",
    "StudentMyId",
    "StudentNote",
    "StudentProfile",
    "StudentDeletionRequest",
    "UrgentReport",
    "StudentGroupMembership",
    "StudentStatus",
    "StudyGroup",
    "Task",
    "TaskAssignment",
    "TaskComment",
    "TaskRow",
    "TaskTemplate",
    "User",
]
