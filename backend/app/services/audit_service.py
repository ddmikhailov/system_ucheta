import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.request_context import get_client_ip
from app.core.time import today_local, utcnow
from app.models import AuditLog, DossierAccessLog, User

# День последней очистки по сроку хранения: удаление идёт не чаще раза в сутки на процесс (процесс один).
_last_purge_day: datetime.date | None = None


def log_action(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: str,
    old_value: str | None = None,
    new_value: str | None = None,
    ip_address: str | None = None,
) -> None:
    # ip_address раньше нигде не передавался ни одним из вызывающих кодов
    # (см. TODO.md 5) — по умолчанию берём его из текущего запроса, вызывающий
    # код может явно переопределить (например, где HTTP-запроса нет).
    entry = AuditLog(
        user_id=user.id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address if ip_address is not None else get_client_ip(),
    )
    db.add(entry)


def redact_audit_history(db: Session, entity_type: str, entity_id: str) -> None:
    """Обезличивание раньше останавливалось на самой записи — старые строки
    audit_log про это же лицо (например, `student.create` хранит ФИО в
    new_value) продолжали хранить настоящее имя даже после анонимизации
    (см. TODO.md 5). Само действие (кто/когда обезличил) не трогаем —
    только значения, которые могли быть ФИО/логином."""
    db.query(AuditLog).filter(
        AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id
    ).update({"old_value": "[обезличено]", "new_value": "[обезличено]"}, synchronize_session=False)


def purge_expired(db: Session) -> int:
    """Удаляет записи журнала действий и журнала просмотров досье старше срока хранения (`AUDIT_RETENTION_DAYS`).
    Возвращает, сколько строк удалено; коммит — за вызывающим."""
    cutoff = utcnow() - datetime.timedelta(days=get_settings().audit_retention_days)
    removed = db.query(AuditLog).filter(AuditLog.created_at < cutoff).delete(synchronize_session=False)
    removed += db.query(DossierAccessLog).filter(DossierAccessLog.created_at < cutoff).delete(synchronize_session=False)
    return removed


def purge_expired_daily(db: Session) -> None:
    """Очистка по сроку хранения раз в сутки — при открытии платформы, как и остальные периодические задачи."""
    global _last_purge_day
    today = today_local()
    if _last_purge_day == today:
        return
    _last_purge_day = today
    if purge_expired(db):
        db.commit()


def reset_purge_throttle() -> None:
    """Только для тестов."""
    global _last_purge_day
    _last_purge_day = None
