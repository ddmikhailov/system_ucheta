"""Массовая загрузка контингента (группы, студенты, кураторы) из единого Excel-шаблона: шаблон, предпросмотр, запись.
Только администратор. Файл передаётся сырым телом запроса (как в загрузке досье), на сервере не сохраняется."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_full_access
from app.db.session import get_db
from app.models import User
from app.services import contingent_import_service as svc
from app.services.audit_service import log_action

router = APIRouter(prefix="/contingent-import", tags=["contingent-import"])

MAX_FILE_BYTES = 5 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ChangeRead(BaseModel):
    sheet: str
    action: str
    label: str
    detail: str


class ErrorRead(BaseModel):
    sheet: str
    row: int
    message: str


class CredentialRead(BaseModel):
    full_name: str
    department: str
    username: str
    password: str


class ReportRead(BaseModel):
    counts: dict[str, int]
    total_changes: int
    changes: list[ChangeRead]
    changes_truncated: bool
    errors: list[ErrorRead]
    warnings: list[str]
    needs_confirmation: str | None
    sheets: list[str]


class ApplyRead(ReportRead):
    credentials: list[CredentialRead]


class ImportParams:
    """Параметры загрузки — в строке запроса, тело запроса занят файлом."""

    def __init__(
        self,
        absent_students: str = Query("keep", pattern="^(keep|expel)$"),
        replace_curators: bool = False,
        create_departments: bool = False,
        confirm_large: bool = False,
        issue_passwords: bool = False,
        default_enrolled_at: datetime.date | None = None,
    ):
        self.options = svc.Options(
            absent_students=absent_students, replace_curators=replace_curators, create_departments=create_departments,
            confirm_large=confirm_large, issue_passwords=issue_passwords, default_enrolled_at=default_enrolled_at,
        )


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_FILE_BYTES:
        raise HTTPException(413, "Файл больше 5 МБ")
    content = await request.body()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл не передан")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "Файл больше 5 МБ")
    return content


def _report_payload(report: svc.Report, parsed: svc.ParsedFile) -> dict:
    return dict(
        counts=report.counts, total_changes=len(report.changes),
        changes=[ChangeRead(**c.__dict__) for c in report.changes[: svc.MAX_CHANGES_LISTED]],
        changes_truncated=len(report.changes) > svc.MAX_CHANGES_LISTED,
        errors=[ErrorRead(**e.__dict__) for e in report.errors[:300]], warnings=report.warnings[:100],
        needs_confirmation=report.needs_confirmation, sheets=parsed.sheets,
    )


def _run(db: Session, user: User, content: bytes, options: svc.Options, commit: bool):
    try:
        parsed = svc.parse_workbook(content)
    except svc.ImportFileError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    try:
        report = svc.process(db, parsed, options, user)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))
    if not commit or report.blocked:
        db.rollback()
    return parsed, report


@router.get("/template")
def template(with_data: bool = True, user: User = Depends(require_full_access), db: Session = Depends(get_db)):
    content = svc.build_template(db, with_data=with_data)
    log_action(db, user, "contingent.template", "contingent", "-", new_value="с данными" if with_data else "пустой")
    db.commit()
    name = "kait20_contingent.xlsx" if with_data else "kait20_contingent_empty.xlsx"
    return Response(content=content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/preview", response_model=ReportRead)
async def preview(
    request: Request, params: ImportParams = Depends(),
    user: User = Depends(require_full_access), db: Session = Depends(get_db),
):
    content = await _read_body(request)
    parsed, report = await run_in_threadpool(_run, db, user, content, params.options, False)
    return ReportRead(**_report_payload(report, parsed))


@router.post("/apply", response_model=ApplyRead)
async def apply(
    request: Request, params: ImportParams = Depends(),
    user: User = Depends(require_full_access), db: Session = Depends(get_db),
):
    content = await _read_body(request)

    def run() -> ApplyRead:
        # Ответ собираем ДО commit(): после него объекты устаревают (см. CLAUDE.md).
        parsed, report = _run(db, user, content, params.options, True)
        if report.errors:
            db.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"В файле {len(report.errors)} ошибок — запись не выполнена. Исправьте их и загрузите файл заново.")
        if report.needs_confirmation:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, report.needs_confirmation)
        payload = _report_payload(report, parsed)
        credentials = [CredentialRead(**c.__dict__) for c in report.credentials]
        summary = "; ".join(f"{k}: {v}" for k, v in report.counts.items()) or "без изменений"
        # Пароли в журнал не попадают — только счётчики.
        log_action(db, user, "contingent.import", "contingent", "-", new_value=summary[:1000])
        db.commit()
        return ApplyRead(**payload, credentials=credentials)

    return await run_in_threadpool(run)
