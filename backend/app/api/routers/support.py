from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limit import check_rate_limit
from app.db.session import get_db
from app.models import User
from app.schemas.support import ClientErrorRequest, ProblemReportRequest, ProblemReportResponse, ReleaseSeenRequest
from app.services import support_service

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/problem-report", response_model=ProblemReportResponse)
def problem_report(payload: ProblemReportRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """«Сообщить о проблеме» из меню пользователя — доступно всем ролям. Лимит защищает колокольчик
    администратора от случайных повторных отправок."""
    if not check_rate_limit(f"problem-report:{user.id}", max_attempts=5, window_seconds=3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много сообщений подряд — попробуйте через час")
    delivered = support_service.report_problem(db, user, payload)
    db.commit()
    return ProblemReportResponse(delivered=delivered)


@router.post("/client-error", status_code=status.HTTP_204_NO_CONTENT)
def client_error(payload: ClientErrorRequest, user: User = Depends(get_current_user)):
    """Ошибка JavaScript в браузере: интерфейс присылает её сам. Сверх лимита молча отбрасываем —
    одна сломанная страница не должна засыпать журнал сервера."""
    if check_rate_limit(f"client-error:{user.id}", max_attempts=20, window_seconds=600):
        support_service.report_client_error(user, payload)


@router.post("/release-seen", status_code=status.HTTP_204_NO_CONTENT)
def release_seen(payload: ReleaseSeenRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Пользователь закрыл плашку «Что нового» этой версии — на других устройствах она тоже не появится."""
    user.seen_release = payload.release
    db.commit()
