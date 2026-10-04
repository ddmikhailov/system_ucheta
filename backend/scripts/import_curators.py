"""Кураторы отделений по списку «ФИО <табуляция> код группы [<табуляция>
отделение]» (по строке на группу; один куратор может вести несколько групп).
Отделение — третья колонка или, если её нет, аргумент командной строки.

Что делает:
  * куратора с таким ФИО в отделении берёт из базы, иначе заводит (роль
    curator, без пароля — пароль потом выдаёт администратор; логин —
    фамилия.инициал латиницей, при совпадении добавляется цифра);
  * код группы ищется в отделении точно или как «код-ГГ» (год набора в
    реестре: «ИБС115» → «ИБС115-26»); не нашлась или неоднозначно — загрузка
    не выполняется вовсе, ничего не записав;
  * назначает куратора на группу с 01.09.2026; если у группы уже есть другой
    действующий куратор — не трогает и сообщает;
  * чужих кураторов и их назначения не меняет; идемпотентен.

Без --apply ничего не пишет:
    python -m scripts.import_curators curators.tsv               # единый файл с колонкой отделения
    python -m scripts.import_curators curators_Кибер.tsv Кибер   # отделение задано аргументом
    ... --apply                                                    # записать
"""
import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import base as db_base
from app.models import AssignmentRole, CuratorAssignment, Department, Role, RoleCode, StudyGroup, User

ASSIGNED_FROM = datetime.date(2026, 9, 1)
YEAR_SUFFIX = re.compile(r"-\d{2}")

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y",
    "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in text.lower() if ch.isalpha() or ch in _TRANSLIT)


def base_username(full_name: str) -> str:
    parts = full_name.split()
    return f"{translit(parts[0])}.{translit(parts[1])[:1]}"


def read_rows(path: str, default_department: str | None) -> list[tuple[str, str, str]]:
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            cells = [c.strip() for c in line.rstrip("\n").split("\t") if c.strip()]
            if len(cells) == 2 and default_department:
                cells.append(default_department)
            if len(cells) != 3 or len(cells[0].split()) < 2:
                raise RuntimeError(
                    f"Строка {number}: нужно «ФИО<табуляция>группа<табуляция>отделение», а там «{line.strip()}»"
                )
            rows.append((" ".join(cells[0].split()), cells[1], cells[2]))
    return rows


def resolve_group(code: str, groups: dict[str, StudyGroup]) -> StudyGroup | None:
    if code in groups:
        return groups[code]
    found = [g for c, g in groups.items() if c.startswith(code) and YEAR_SUFFIX.fullmatch(c[len(code):])]
    return found[0] if len(found) == 1 else None


def run(path: str, department_name: str | None, apply: bool) -> dict[str, int]:
    rows = read_rows(path, department_name)
    db = db_base.SessionLocal()
    stats: dict[str, int] = {}

    def count(name: str) -> None:
        stats[name] = stats.get(name, 0) + 1

    try:
        role = db.query(Role).filter(Role.code == RoleCode.CURATOR.value).one_or_none()
        if role is None:
            raise RuntimeError("Роль curator не найдена — сначала запустите scripts.seed")
        departments = {d.name: d for d in db.query(Department).all()}
        unknown = sorted({dept for _, _, dept in rows if dept not in departments})
        if unknown:
            raise RuntimeError(f"Отделение не найдено: {', '.join(unknown)} — сначала загрузите реестр.")

        groups_by_dept = {
            name: {g.code: g for g in db.query(StudyGroup).filter(StudyGroup.department_id == d.id)}
            for name, d in departments.items()
        }
        problems = []
        resolved = []
        for full_name, code, dept in rows:
            group = resolve_group(code, groups_by_dept[dept])
            if group is None:
                problems.append(f"{code} ({dept})")
            else:
                resolved.append((full_name, group, departments[dept]))
        if problems:
            raise RuntimeError(f"Нет однозначной группы для кодов: {', '.join(problems)}. Ничего не записано.")

        users_by_key = {
            (u.department_id, u.full_name): u for u in db.query(User).filter(User.department_id.isnot(None))
        }
        taken = {u for (u,) in db.query(User.username).all()}
        for full_name, group, department in resolved:
            user = users_by_key.get((department.id, full_name))
            if user is None:
                username = candidate = base_username(full_name)
                suffix = 1
                while username in taken:
                    suffix += 1
                    username = f"{candidate}{suffix}"
                taken.add(username)
                user = User(username=username, full_name=full_name, role_id=role.id,
                            department_id=department.id, password_hash=None)
                db.add(user)
                db.flush()
                users_by_key[(department.id, full_name)] = user
                count("кураторов создано")

            active = (
                db.query(CuratorAssignment)
                .filter(CuratorAssignment.study_group_id == group.id,
                        CuratorAssignment.role_type == AssignmentRole.CURATOR,
                        CuratorAssignment.end_date.is_(None))
                .all()
            )
            if any(a.user_id == user.id for a in active):
                continue
            if active:
                print(f"! у группы {group.code} уже есть другой куратор — не трогаю")
                count("групп пропущено (уже есть куратор)")
                continue
            db.add(CuratorAssignment(study_group_id=group.id, user_id=user.id,
                                     role_type=AssignmentRole.CURATOR, start_date=ASSIGNED_FROM))
            count("назначений создано")

        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    print("Загружено." if apply else "Проверка (ничего не записано; добавьте --apply):")
    for name, value in stats.items():
        print(f"  {name}: {value}")
    print(f"  строк в списке: {len(rows)}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="файл «ФИО<табуляция>группа[<табуляция>отделение]»")
    parser.add_argument("department", nargs="?", help="отделение, если в файле нет третьей колонки")
    parser.add_argument("--apply", action="store_true", help="записать изменения в базу")
    args = parser.parse_args()
    run(args.path, args.department, args.apply)


if __name__ == "__main__":
    main()
