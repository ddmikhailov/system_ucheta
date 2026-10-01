import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import (
    assert_can_access_group,
    get_current_user,
    require_management,
    scope_department_id,
    validate_date_range,
)
from app.db.session import get_db
from app.models import StudyGroup, User
from app.services import export_service

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/excel")
def export_excel(
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
    course: int | None = None,
    study_group_id: int | None = None,
    pair: int = Query(default=1, ge=1, le=10),
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    validate_date_range(date_from, date_to)
    scope = scope_department_id(user, department_id)
    content = export_service.build_summary_workbook(
        db, date_from, date_to, scope, course=course, study_group_id=study_group_id, pair=pair
    )
    filename = f"itog_{date_from}_{date_to}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pdf/{study_group_id}")
def export_pdf(
    study_group_id: int,
    date_from: datetime.date,
    date_to: datetime.date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    validate_date_range(date_from, date_to)
    assert_can_access_group(db, user, study_group_id, date_to)
    if db.get(StudyGroup, study_group_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    content = export_service.build_signature_pdf(db, study_group_id, date_from, date_to)
    filename = f"tabel_{study_group_id}_{date_from}_{date_to}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
