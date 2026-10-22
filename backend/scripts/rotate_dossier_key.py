"""Перешифровать особые поля досье новым ключом — второй шаг смены DOSSIER_ENCRYPTION_KEY.

Перед запуском в DOSSIER_ENCRYPTION_KEY должны стоять через запятую оба ключа: «новый,старый». Скрипт читает
каждую запись под любым из них и записывает под новым; содержимое не меняется. После --apply старый ключ из
списка можно убрать (и только после этого). Запись, которую не читает ни один ключ, не трогается и попадает
в отчёт. Повторный запуск безопасен. Порядок целиком — docs/deploy/kait20-klyuch-dosie.txt.

    python -m scripts.rotate_dossier_key            # проверка: все ли записи читаются
    python -m scripts.rotate_dossier_key --apply    # перешифровать
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import update

from app.core import field_crypto
from app.db import base as db_base
from app.models import StudentProfile
from app.services import audit_service


def run(apply: bool) -> dict[str, int]:
    if not field_crypto.is_available():
        raise SystemExit("DOSSIER_ENCRYPTION_KEY не задан или некорректен — нечем перешифровывать.")
    db = db_base.SessionLocal()
    stats = {"перешифровано": 0, "не читается ни одним ключом": 0}
    try:
        rows = (
            db.query(StudentProfile.student_id, StudentProfile.special_enc, StudentProfile.updated_at)
            .filter(StudentProfile.special_enc.is_not(None))
            .all()
        )
        for student_id, token, updated_at in rows:
            try:
                rotated = field_crypto.rotate(token)
            except field_crypto.EncryptionUnavailable:
                stats["не читается ни одним ключом"] += 1
                print(f"  ! студент {student_id}: запись не читается ни одним ключом, оставлена как есть")
                continue
            # updated_at — явно прежний: содержимое досье не менялось, «обновлено» в карточке не должно сдвинуться.
            db.execute(
                update(StudentProfile)
                .where(StudentProfile.student_id == student_id)
                .values(special_enc=rotated, updated_at=updated_at)
            )
            stats["перешифровано"] += 1
        if apply:
            audit_service.log_action(db, None, "dossier.key_rotate", "student_profile", "*",
                                     new_value=str(stats["перешифровано"]))
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    print("Готово." if apply else "Проверка (ничего не записано; добавьте --apply):")
    print(f"  ключей в DOSSIER_ENCRYPTION_KEY: {field_crypto.key_count()}")
    for name, value in stats.items():
        print(f"  {name}: {value}")
    if field_crypto.key_count() < 2:
        print("  Ключ один — перешифровывать нечем: допишите старый ключ после нового через запятую.")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="записать изменения в базу")
    run(parser.parse_args().apply)


if __name__ == "__main__":
    main()
