import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, get_current_user, require_meal_viewer
from app.core.roles import DEPARTMENT_SCOPED_ROLES
from app.core.time import now_local, utc_to_local
from app.core.xlsx import append_row
from app.db.session import get_db
from app.models import RoleCode, StudyGroup, User
from app.schemas.meals import (
    GroupMealsRead, MealDayRead, MealOverview, MealOverviewDay, MealOverviewRow, MealSetDay, MealSetStudent,
    MealStudentRead, MealSubmitWeek, MealWeekRead,
)
from app.services import meal_service
from app.services.access_service import get_curator_group_ids

router = APIRouter(prefix="/meals", tags=["meals"])


def _curator_name(group: StudyGroup, today: datetime.date) -> str | None:
    a = next((a for a in group.curator_assignments if a.is_active_on(today) and a.role_type.value == "curator" and a.user.is_active), None)
    return a.user.full_name if a else None


def _week_read(week: meal_service.GroupWeek) -> MealWeekRead:
    return MealWeekRead(
        week_start=week.week_start, status=week.status, deadline=week.deadline,
        submitted_count=week.submission.count if week.submission else None,
        submitted_at=utc_to_local(week.submission.submitted_at) if week.submission else None,
        forecast=week.forecast,
        days=[MealDayRead(date=d.date, count=d.count, source=d.source, open=d.open, cutoff=d.cutoff) for d in week.days],
    )


def _group_access(db: Session, user: User, group_id: int) -> tuple[StudyGroup, bool]:
    """(группа, можно ли править). Видят свод роли из MEAL_VIEW_ROLES (зав. отделением и тьютор — своё отделение);
    править может тот, у кого есть доступ к группе как к журналу: куратор группы, администрация."""
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    role = RoleCode(user.role.code)
    if role == RoleCode.MEAL_MANAGER:
        return group, False
    assert_can_access_group(db, user, group_id, now_local().date())
    return group, True


@router.get("/groups/{group_id}", response_model=GroupMealsRead)
def group_meals(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group, can_edit = _group_access(db, user, group_id)
    now = now_local()
    today = now.date()
    states = meal_service.student_states(db, [group], today)[group.id]
    this_week = meal_service.week_start(today)
    weeks = meal_service.build_weeks(db, [group], this_week, now)[group.id], meal_service.build_weeks(
        db, [group], this_week + datetime.timedelta(days=7), now)[group.id]
    base = weeks[1]
    return GroupMealsRead(
        study_group_id=group.id, code=group.code, funding=group.funding, can_edit=can_edit,
        eaters=base.eaters,
        students=[MealStudentRead(student_id=s.student.id, full_name=s.student.full_name, eats=s.eats, locked_reason=s.locked_reason) for s in states],
        attendance_percent=base.percent, hint=base.hint, weeks=[_week_read(w) for w in weeks],
    )


@router.put("/groups/{group_id}/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def set_student(group_id: int, student_id: int, payload: MealSetStudent, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group, can_edit = _group_access(db, user, group_id)
    if not can_edit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
    meal_service.set_student_eats(db, user, group, student_id, payload.eats)
    db.commit()


@router.post("/groups/{group_id}/week", response_model=MealWeekRead)
def submit_week(group_id: int, payload: MealSubmitWeek, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group, can_edit = _group_access(db, user, group_id)
    if not can_edit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
    week = meal_service.submit_week(db, user, group, payload.week_start, payload.count)
    result = _week_read(week)
    db.commit()
    return result


@router.put("/groups/{group_id}/day", response_model=MealWeekRead)
def set_day(group_id: int, payload: MealSetDay, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group, can_edit = _group_access(db, user, group_id)
    if not can_edit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
    week = meal_service.set_day_count(db, user, group, payload.date, payload.count)
    result = _week_read(week)
    db.commit()
    return result


def _overview(db: Session, user: User, week: datetime.date, department_id: int | None) -> MealOverview:
    if week.weekday() != 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неделя начинается с понедельника")
    now = now_local()
    groups = [g for g in meal_service.visible_groups(db, user, department_id) if g.funding != "contract"]
    weeks = meal_service.build_weeks(db, groups, week, now)
    rows, totals, dates = [], {}, set()
    for group in groups:
        w = weeks[group.id]
        if w.eaters == 0:
            continue
        rows.append(MealOverviewRow(
            study_group_id=group.id, code=group.code, course=group.course, department_id=group.department_id,
            department_name=group.department.name, curator_name=_curator_name(group, now.date()), eaters=w.eaters,
            attendance_percent=w.percent, status=w.status,
            submitted_at=utc_to_local(w.submission.submitted_at) if w.submission else None,
            days=[MealOverviewDay(date=d.date, count=d.count, source=d.source) for d in w.days],
        ))
        for d in w.days:
            dates.add(d.date)
            totals[d.date.isoformat()] = totals.get(d.date.isoformat(), 0) + d.count
    return MealOverview(week_start=week, deadline=meal_service.submit_deadline(week), dates=sorted(dates), rows=rows, totals=totals)


@router.get("/overview", response_model=MealOverview)
def overview(
    week_start: datetime.date, department_id: int | None = None,
    user: User = Depends(require_meal_viewer), db: Session = Depends(get_db),
):
    return _overview(db, user, week_start, department_id)


@router.get("/export")
def export_week(
    week_start: datetime.date, department_id: int | None = None,
    user: User = Depends(require_meal_viewer), db: Session = Depends(get_db),
):
    data = meal_service.export_workbook(_overview(db, user, week_start, department_id))
    name = f"pitanie_{week_start.isoformat()}.xlsx"
    return Response(
        content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
