"""«Папка куратора»: 16 документов п. 5.1 положения о кураторе в одном месте, у каждого — выгрузка.

Права — как у чтения группы (`assert_can_view_group`): куратор и заместитель — свои группы, зав. отделением и тьютор —
отделение, воспитательный отдел, админ, соц. педагог и психолог — весь колледж. Содержимое документов эндпоинт не
отдаёт: только список с состоянием и ссылками, а сама выгрузка проверяет права по-своему (паспорт, карточки, беседы)."""
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import assert_can_view_group, get_current_user, require_module
from app.core import field_crypto
from app.core.time import today_local
from app.db.session import get_db
from app.models import DossierAccessLog, StudyGroup, User
from app.services import folder_service, group_event_service, ivpr_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/folder", tags=["folder"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DownloadRead(BaseModel):
    label: str
    path: str
    filename: str


class FolderItemRead(BaseModel):
    code: str
    title: str
    state: Literal["filled", "blank", "outside", "off"]
    note: str
    downloads: list[DownloadRead]
    open_tab: str | None
    open_part: str | None
    can_add: str | None


class FolderRead(BaseModel):
    group_id: int
    group_code: str
    school_year: str
    items: list[FolderItemRead]


def _group(db: Session, group_id: int) -> StudyGroup:
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    return group


@router.get("/groups/{group_id}", response_model=FolderRead)
def group_folder(
    group_id: int, year: str | None = Query(None, max_length=9),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    year = year or group_event_service.school_year(today)
    if not group_event_service.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    items = folder_service.build(db, group, year, today)
    return FolderRead(
        group_id=group.id, group_code=group.code, school_year=year,
        items=[FolderItemRead(**vars(i) | {"downloads": [DownloadRead(**vars(d)) for d in i.downloads]}) for i in items],
    )


@router.get("/groups/{group_id}/ivpr.docx", dependencies=[Depends(require_module("dossier"))])
def group_ivpr(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Копия плана ИВПР (п. 5.1.11). Признак «внутренний учёт» — особые данные досье, поэтому, как соц. паспорт,
    выгрузка пишет в журнал просмотров запись на каждого студента, попавшего в документ."""
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    if not field_crypto.is_available():
        raise HTTPException(status.HTTP_409_CONFLICT, "Документ недоступен: на сервере не задан ключ шифрования досье")
    try:
        students = ivpr_service.collect(db, group, today)
    except ivpr_service.SpecialDataUnavailable:
        raise HTTPException(status.HTTP_409_CONFLICT, "Документ недоступен: на сервере не задан ключ шифрования досье")
    curator = next(
        (a.user.full_name for a in group.curator_assignments
         if a.role_type.value == "curator" and a.is_active_on(today) and a.user.is_active), None,
    )
    content = ivpr_service.build_docx(group.code, curator, today, students)
    db.add_all(DossierAccessLog(student_id=s.student_id, user_id=user.id, included_special=True) for s in students)
    log_action(db, user, "folder.ivpr_docx", "study_group", str(group.id), new_value=str(len(students)))
    db.commit()
    filename = quote(f"План_ИВПР_{group.code}_{today:%d.%m.%Y}.docx")
    return Response(content=content, media_type=DOCX_MEDIA_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})
