import enum


class RoleCode(str, enum.Enum):
    CURATOR = "curator"
    DEPUTY_CURATOR = "deputy_curator"
    DEPT_HEAD = "dept_head"
    EDU_DEPARTMENT = "edu_department"
    ADMIN = "admin"


class StudentStatus(str, enum.Enum):
    STUDYING = "studying"
    ACADEMIC_LEAVE = "academic_leave"
    EXPELLED = "expelled"


class AssignmentRole(str, enum.Enum):
    CURATOR = "curator"
    DEPUTY = "deputy"


class DayType(str, enum.Enum):
    STUDY_DAY = "study_day"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"
    VACATION = "vacation"


class MarkSource(str, enum.Enum):
    MANUAL = "manual"
    PERIOD = "period"


class BasisStatus(str, enum.Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    OVERDUE = "overdue"
