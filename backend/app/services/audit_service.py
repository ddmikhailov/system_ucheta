from sqlalchemy.orm import Session

from app.core.request_context import get_client_ip
from app.models import AuditLog, User


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
