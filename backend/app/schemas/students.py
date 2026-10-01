import datetime

from pydantic import BaseModel


class StudentCardGroup(BaseModel):
    id: int
    code: str
    course: int
    study_form: str | None
    is_active: bool
    department_id: int
    department_name: str


class StudentCardMembership(BaseModel):
    group_id: int
    group_code: str
    start_date: datetime.date
    end_date: datetime.date | None


class StudentCardMark(BaseModel):
    date: datetime.date
    code: str
    name: str
    comment: str | None
    basis_reference: str | None


class StudentCardStats(BaseModel):
    date_from: datetime.date
    date_to: datetime.date
    in_list: int
    present: int
    absent_total: int
    absent_excused: int
    absent_unexcused: int
    late: int
    percent: float
    by_code: dict[str, int]


class StudentCard(BaseModel):
    id: int
    full_name: str
    last_name: str
    first_name: str
    middle_name: str | None
    status: str
    enrolled_at: datetime.date
    left_at: datetime.date | None
    group: StudentCardGroup
    curator_name: str | None
    deputy_name: str | None
    group_history: list[StudentCardMembership]
    stats: StudentCardStats
    recent_marks: list[StudentCardMark]


class StudentDayAttendance(BaseModel):
    date: datetime.date
    # study_day / remote / weekend / holiday / vacation / not_enrolled
    day_type: str
    # present — присутствовал (день сдан, отметки нет); mark — стоит отметка;
    # not_submitted — учебный день, но группа его не сдала; none — не учебный
    # день или студент ещё/уже не числился.
    status: str
    group_code: str | None = None
    mark_code: str | None = None
    mark_name: str | None = None
    counts_as_present: bool | None = None
    is_excused: bool | None = None
    comment: str | None = None
    basis_reference: str | None = None


class StudentMonthSummary(BaseModel):
    study_days: int
    present: int
    absent: int
    absent_excused: int
    absent_unexcused: int
    late: int
    not_submitted: int
    percent: float | None
    by_code: dict[str, int]


class StudentMonthAttendance(BaseModel):
    student_id: int
    year: int
    month: int
    first_month: str  # YYYY-MM — самый ранний месяц, который имеет смысл листать
    summary: StudentMonthSummary
    days: list[StudentDayAttendance]
