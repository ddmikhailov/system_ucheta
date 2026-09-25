import enum


class RoleCode(str, enum.Enum):
    CURATOR = "curator"
    DEPUTY_CURATOR = "deputy_curator"
    DEPT_HEAD = "dept_head"
    EDU_DEPARTMENT = "edu_department"
    ADMIN = "admin"
    # Полный доступ по всему колледжу, как у admin (см. обновление 1.2) —
    # отдельная роль, а не просто звание, в отличие от display_title у
    # dept_head: тьютору нужны реально те же права, что у администратора,
    # а не только другая подпись.
    TUTOR = "tutor"


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
    # Электронная форма обучения — дистанционный учебный день: считается
    # учебным для посещаемости, но отдельно помечается в календаре.
    REMOTE = "remote"


class MarkSource(str, enum.Enum):
    MANUAL = "manual"
    PERIOD = "period"


class BasisStatus(str, enum.Enum):
    NOT_REQUIRED = "not_required"
    CONFIRMED = "confirmed"
