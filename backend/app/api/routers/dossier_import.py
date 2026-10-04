"""Массовая загрузка досье из Excel: шаблон, предпросмотр, применение.
Файл передаётся сырым телом запроса (без multipart — лишняя зависимость не нужна)."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_viewer
from app.db.session import get_db
from app.models import User
from app.services import dossier_import_service as svc

router = APIRouter(prefix="/dossier-import", tags=["dossier-import"])

MAX_FILE_BYTES = 5 * 1024 * 1024
PREVIEW_ROWS_LIMIT = 300


class PreviewRow(BaseModel):
    row: int
    label: str
    errors: list[str]
    will_update: bool


class PreviewResponse(BaseModel):
    total: int
    ready: int
    unchanged: int
    with_errors: int
    rows: list[PreviewRow]  # ошибки первыми, не больше PREVIEW_ROWS_LIMIT


class ApplyResponse(BaseModel):
    updated: int
    skipped_with_errors: int


async def _read_body(request: Request) -> bytes:
    # Не читаем тело, если клиент сразу заявил слишком большой размер.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 5 МБ")
    content = await request.body()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл не передан")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 5 МБ")
    return content


def _parse(db: Session, user: User, content: bytes) -> list[svc.RowResult]:
    try:
        return svc.parse_workbook(db, user, content)
    except svc.ImportFileError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/template")
def template(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    content = svc.build_template(db, user)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="dossier_template.xlsx"'},
    )


@router.post("/preview", response_model=PreviewResponse)
async def preview(request: Request, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    content = await _read_body(request)
    results = await run_in_threadpool(_parse, db, user, content)
    errors = [r for r in results if r.errors]
    ready = [r for r in results if not r.errors and r.has_changes]
    listed = (errors + ready)[:PREVIEW_ROWS_LIMIT]
    return PreviewResponse(
        total=len(results), ready=len(ready), with_errors=len(errors),
        unchanged=len(results) - len(errors) - len(ready),
        rows=[PreviewRow(row=r.row, label=r.label, errors=r.errors, will_update=not r.errors) for r in listed],
    )


@router.post("/apply", response_model=ApplyResponse)
async def apply(request: Request, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    content = await _read_body(request)

    def run() -> ApplyResponse:
        results = _parse(db, user, content)
        updated = svc.apply_results(db, user, results)
        return ApplyResponse(updated=updated, skipped_with_errors=sum(1 for r in results if r.errors))

    return await run_in_threadpool(run)
