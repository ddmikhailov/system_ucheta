"""Скрыть (архивировать) группы со строчной «о» в коде («ИСПо212», «РУо112»,
«ГДоз226д») — они не учитываются нигде: ни в общих перечнях, ни среди
вакантных групп.

Группы без куратора этим скриптом НЕ скрываются: они выпадают из общих
перечней сами (app/services/group_scope.py) и показываются на вкладке
«Вакантные группы».

Скрытая группа (is_active = false) пропадает из списков, «Свода», статистики и
выгрузок; студенты, отметки и история остаются, группу можно вернуть в работу
в админ-панели. Идемпотентен:

    python -m scripts.hide_groups            # проверка
    python -m scripts.hide_groups --apply    # скрыть
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import base as db_base
from app.models import StudyGroup
from app.services import audit_service

LOWERCASE_O = "о"  # кириллическая


def run(apply: bool) -> dict[str, int]:
    db = db_base.SessionLocal()
    stats = {"скрыто (строчная «о» в коде)": 0}
    hidden_codes = []
    try:
        for group in db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).order_by(StudyGroup.code):
            if LOWERCASE_O not in group.code:
                continue
            group.is_active = False
            stats["скрыто (строчная «о» в коде)"] += 1
            hidden_codes.append(group.code)
            audit_service.log_action(db, None, "group.archive", "study_group", str(group.id),
                                     old_value="active", new_value="строчная «о» в коде")
        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    print("Скрыто." if apply else "Проверка (ничего не записано; добавьте --apply):")
    for name, value in stats.items():
        print(f"  {name}: {value}")
    if hidden_codes:
        print("  группы: " + ", ".join(hidden_codes))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="записать изменения в базу")
    run(parser.parse_args().apply)


if __name__ == "__main__":
    main()
