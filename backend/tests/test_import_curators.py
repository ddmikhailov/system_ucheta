"""Назначение кураторов по списку: синтетические ФИО."""
import datetime

import pytest

import scripts.import_curators as curators
from app.models import AssignmentRole, CuratorAssignment, Department, Role, RoleCode, StudyGroup, User


@pytest.fixture()
def kiber(seeded, db):
    department = Department(name="Кибер")
    db.add(department)
    db.flush()
    for code in ("ИБС115-26", "ИБС135-26", "ИБС315-24", "ИБС315д-24"):
        db.add(StudyGroup(code=code, course=1, department_id=department.id))
    db.commit()
    return department


def write_list(tmp_path, lines):
    path = tmp_path / "curators.tsv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_creates_curators_and_assigns_groups_by_code_with_year(kiber, db, tmp_path):
    path = write_list(tmp_path, [
        "Комлев Глеб Сергеевич\tИБС115",
        "Комлев Глеб Сергеевич\tИБС135",
        "Егорова Наталья Владимировна\tИБС315",
        "Иванова Елена Михайловна\tИБС315д",
    ])

    stats = curators.run(path, "Кибер", apply=True)

    assert stats == {"кураторов создано": 3, "назначений создано": 4}
    komlev = db.query(User).filter_by(full_name="Комлев Глеб Сергеевич").one()
    assert komlev.username == "komlev.g" and komlev.password_hash is None
    assert komlev.department_id == kiber.id
    assert db.get(Role, komlev.role_id).code == RoleCode.CURATOR.value
    codes = {a.study_group.code for a in db.query(CuratorAssignment).filter_by(user_id=komlev.id)}
    assert codes == {"ИБС115-26", "ИБС135-26"}
    assert all(a.start_date == datetime.date(2026, 9, 1) and a.role_type == AssignmentRole.CURATOR
               for a in db.query(CuratorAssignment))


def test_second_run_and_dry_run_change_nothing(kiber, db, tmp_path):
    path = write_list(tmp_path, ["Комлев Глеб Сергеевич\tИБС115"])

    curators.run(path, "Кибер", apply=False)
    assert db.query(CuratorAssignment).count() == 0 and db.query(User).filter_by(username="komlev.g").count() == 0

    curators.run(path, "Кибер", apply=True)
    assert curators.run(path, "Кибер", apply=True) == {}
    assert db.query(CuratorAssignment).count() == 1


def test_username_collision_gets_a_number(kiber, db, tmp_path):
    role = db.query(Role).filter_by(code=RoleCode.CURATOR.value).one()
    db.add(User(username="komlev.g", full_name="Другой Глеб", role_id=role.id, password_hash=None))
    db.commit()

    curators.run(write_list(tmp_path, ["Комлев Глеб Сергеевич\tИБС115"]), "Кибер", apply=True)

    assert db.query(User).filter_by(full_name="Комлев Глеб Сергеевич").one().username == "komlev.g2"


def test_existing_other_curator_is_not_replaced(kiber, db, tmp_path):
    curators.run(write_list(tmp_path, ["Первый Куратор Иванович\tИБС115"]), "Кибер", apply=True)

    stats = curators.run(write_list(tmp_path, ["Второй Куратор Петрович\tИБС115"]), "Кибер", apply=True)

    assert stats["групп пропущено (уже есть куратор)"] == 1
    group = db.query(StudyGroup).filter_by(code="ИБС115-26").one()
    assert db.query(CuratorAssignment).filter_by(study_group_id=group.id).count() == 1


def test_unknown_group_aborts_everything(kiber, db, tmp_path):
    path = write_list(tmp_path, ["Комлев Глеб Сергеевич\tИБС115", "Кто-то Иван\tНЕТ999"])

    with pytest.raises(RuntimeError, match="НЕТ999"):
        curators.run(path, "Кибер", apply=True)

    assert db.query(CuratorAssignment).count() == 0 and db.query(User).filter_by(username="komlev.g").count() == 0


def test_unified_file_with_department_column_covers_several_departments(kiber, db, tmp_path):
    techno = Department(name="Техно")
    db.add(techno)
    db.flush()
    db.add(StudyGroup(code="КСК114-26", course=1, department_id=techno.id))
    db.commit()
    path = write_list(tmp_path, [
        "Комлев Глеб Сергеевич	ИБС115	Кибер",
        "Гусева Мария Валерьевна	КСК114	Техно",
    ])

    stats = curators.run(path, None, apply=True)

    assert stats == {"кураторов создано": 2, "назначений создано": 2}
    assert db.query(User).filter_by(full_name="Гусева Мария Валерьевна").one().department_id == techno.id


def test_group_is_looked_up_only_inside_its_department(kiber, db, tmp_path):
    db.add(Department(name="Техно"))
    db.commit()

    with pytest.raises(RuntimeError, match=r"ИБС115 \(Техно\)"):
        curators.run(write_list(tmp_path, ["Комлев Глеб Сергеевич	ИБС115	Техно"]), None, apply=True)


def test_unknown_department_and_bad_line(kiber, db, tmp_path):
    with pytest.raises(RuntimeError, match="Отделение не найдено"):
        curators.run(write_list(tmp_path, ["Комлев Глеб\tИБС115"]), "Нет такого", apply=True)
    with pytest.raises(RuntimeError, match="Строка 1"):
        curators.run(write_list(tmp_path, ["только-одна-колонка"]), "Кибер", apply=True)


def test_transliteration_matches_existing_username_style():
    assert curators.base_username("Безрукавникова Анастасия Сергеевна") == "bezrukavnikova.a"
    assert curators.base_username("Волкова Юлия Александровна") == "volkova.y"
    assert curators.base_username("Михалёва Александра Валентиновна") == "mikhaleva.a"
    assert curators.base_username("Шкуренко Андрей Игоревич") == "shkurenko.a"


def test_issue_passwords_only_with_apply_and_to_curators_without_one(kiber, db, tmp_path):
    from app.core.security import verify_password

    path = write_list(tmp_path, ["Комлев Глеб Сергеевич\tИБС115", "Егорова Наталья Владимировна\tИБС315"])
    out = tmp_path / "passwords.csv"

    stats = curators.run(path, "Кибер", apply=False, issue_passwords_file=str(out))
    assert not out.exists() and "временных паролей выдано" not in stats  # проверка ничего не выдаёт

    stats = curators.run(path, "Кибер", apply=True, issue_passwords_file=str(out))
    assert stats["временных паролей выдано"] == 2
    rows = [line.split(";") for line in out.read_text(encoding="utf-8-sig").splitlines()]
    assert rows[0] == ["ФИО", "Отделение", "Логин", "Временный пароль"] and len(rows) == 3
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    by_login = {r[2]: r[3] for r in rows[1:]}
    komlev = db.query(User).filter_by(username="komlev.g").one()
    assert komlev.must_change_password and verify_password(by_login["komlev.g"], komlev.password_hash)

    # повторный запуск паролей не меняет и новых не выдаёт
    out2 = tmp_path / "again.csv"
    stats = curators.run(path, "Кибер", apply=True, issue_passwords_file=str(out2))
    assert "временных паролей выдано" not in stats and not out2.exists()


def test_assigned_from_and_report_file(kiber, db, tmp_path):
    path = write_list(tmp_path, ["Комлев Глеб Сергеевич\tИБС115"])
    report = tmp_path / "r.txt"
    curators.run(path, "Кибер", apply=True, assigned_from=datetime.date(2027, 9, 1), report=str(report))
    assert db.query(CuratorAssignment).one().start_date == datetime.date(2027, 9, 1)
    assert "кураторов создано: 1" in report.read_text(encoding="utf-8")
