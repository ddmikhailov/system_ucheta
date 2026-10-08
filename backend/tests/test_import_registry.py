"""Загрузка реестра контингента: синтетический реестр (выдуманные ФИО)."""
import datetime

import openpyxl
import pytest

import scripts.import_registry as registry
from app.models import (
    AssignmentRole, CuratorAssignment, Department, Role, RoleCode, Student, StudentGroupMembership,
    StudentStatus, StudyGroup, User, AttendanceMark, AuditLog, MarkCode,
)

DIGITAL = "город Москва, улица 1-я Мясниковская, дом 16"
CYBER = "город Москва, шоссе Щёлковское, дом 52"
TODAY = datetime.date(2026, 10, 1)
HEADER = ["ФИО", "Дата рождения", "Пол", "Статус обучения", "Финансирование", "Спецпрограмма",
          "Учебная группа", "Адрес площадки", "Курс обучения", "Специальность", "Код"]


def make_registry(tmp_path, people):
    """people: (ФИО, статус, группа, адрес, курс)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Реестр контингента"])
    ws.append(HEADER)
    for fio, status, group, address, course in people:
        ws.append([fio, "01.01.2008", "Мужской", status, "Бюджет", "Нет", group, address, f"{course} курс", "Спец", "09.02.07"])
    path = tmp_path / "registry.xlsx"
    wb.save(path)
    return str(path)


def digital_group(db, code, course, students):
    department = db.query(Department).filter_by(name="Диджитал").one()
    group = StudyGroup(code=code, course=course, department_id=department.id)
    db.add(group)
    db.flush()
    for last, first, middle in students:
        student = Student(last_name=last, first_name=first, middle_name=middle,
                          study_group_id=group.id, enrolled_at=datetime.date(2026, 9, 1))
        db.add(student)
        db.flush()
        db.add(StudentGroupMembership(student_id=student.id, study_group_id=group.id,
                                      start_date=student.enrolled_at))
    db.commit()
    return group


def test_creates_departments_groups_and_students_by_address(seeded, db, tmp_path):
    path = make_registry(tmp_path, [
        ("Иванов Иван Иванович", "Обучается", "КИБ111-26", CYBER, 1),
        ("Петрова Анна", "В академическом отпуске", "КИБ111-26", CYBER, 1),
        ("Сидоров Реджеб Несими Оглы", "Обучается", "ИСП211-25", DIGITAL, 2),
    ])

    stats = registry.run(path, apply=True, today=TODAY)

    assert db.query(Department).filter_by(name="Кибер").count() == 1
    group = db.query(StudyGroup).filter_by(code="КИБ111").one()
    assert group.course == 1 and group.department.name == "Кибер"
    leave = db.query(Student).filter_by(last_name="Петрова").one()
    assert leave.status == StudentStatus.ACADEMIC_LEAVE and leave.middle_name is None
    oglu = db.query(Student).filter_by(last_name="Сидоров").one()
    assert (oglu.first_name, oglu.middle_name) == ("Реджеб", "Несими Оглы")
    assert stats["студентов создано"] == 3 and stats["групп создано"] == 2
    memberships = db.query(StudentGroupMembership).count()
    assert memberships == 3


def test_dry_run_changes_nothing(seeded, db, tmp_path):
    path = make_registry(tmp_path, [("Иванов Иван Иванович", "Обучается", "КИБ111-26", CYBER, 1)])

    registry.run(path, apply=False, today=TODAY)

    db.expire_all()
    assert db.query(Student).count() == 0
    assert db.query(StudyGroup).count() == 0
    assert db.query(Department).filter_by(name="Кибер").count() == 0


def test_second_run_changes_nothing(seeded, db, tmp_path):
    path = make_registry(tmp_path, [
        ("Иванов Иван Иванович", "Обучается", "КИБ111-26", CYBER, 1),
        ("Петрова Анна", "В академическом отпуске", "КИБ111-26", CYBER, 1),
    ])
    registry.run(path, apply=True, today=TODAY)

    stats = registry.run(path, apply=True, today=TODAY)

    assert stats == {}


def test_legacy_group_is_renamed_keeping_curator_and_students(seeded, db, tmp_path):
    group = digital_group(db, "ИИ112-26", 1, [("Иванов", "Иван", "Иванович"), ("Петров", "Пётр", None)])
    curator_role = db.query(Role).filter_by(code=RoleCode.CURATOR.value).one()
    curator = User(username="cur", full_name="Куратор Тест", role_id=curator_role.id,
                   department_id=group.department_id, password_hash=None)
    db.add(curator)
    db.flush()
    db.add(CuratorAssignment(study_group_id=group.id, user_id=curator.id,
                             role_type=AssignmentRole.CURATOR, start_date=datetime.date(2026, 9, 1)))
    db.commit()
    path = make_registry(tmp_path, [
        ("Иванов Иван Иванович", "Обучается", "ИИ112-26", DIGITAL, 1),
        ("Петров Пётр", "Обучается", "ИИ112-26", DIGITAL, 1),
        ("Новикова Мария Сергеевна", "Обучается", "ИИ112-26", DIGITAL, 1),
    ])

    stats = registry.run(path, apply=True, today=TODAY)

    db.expire_all()
    assert db.query(StudyGroup).filter_by(code="ИИ112-26").count() == 0
    renamed = db.query(StudyGroup).filter_by(code="ИИ112").one()
    assert renamed.id == group.id
    assert db.query(CuratorAssignment).filter_by(study_group_id=group.id).count() == 1
    assert db.query(Student).filter_by(study_group_id=group.id).count() == 3
    assert stats["групп переименовано"] == 1 and stats["студентов создано"] == 1


def test_code_suffixes_are_dropped_and_subgroups_merge_into_the_main_group(seeded, db, tmp_path):
    main = digital_group(db, "ИИ112-26", 1, [("Иванов", "Иван", None), ("Петров", "Пётр", None)])
    sub_group = digital_group(db, "ИИ112.8", 1, [("Сидоров", "Семён", None)])
    path = make_registry(tmp_path, [
        ("Иванов Иван", "Обучается", "ИИ112-26", DIGITAL, 1),
        ("Петров Пётр", "Обучается", "ИИ112-26", DIGITAL, 1),
        ("Сидоров Семён", "Обучается", "ИИ112.8", DIGITAL, 1),
    ])

    registry.run(path, apply=True, today=TODAY)

    db.expire_all()
    merged = db.query(StudyGroup).filter_by(code="ИИ112").one()
    assert merged.id == main.id and merged.is_active is True
    assert db.query(Student).filter_by(study_group_id=main.id).count() == 3
    assert db.get(StudyGroup, sub_group.id).is_active is False
    assert db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).count() == 1
    assert registry.normalize_code("ИБС155.7") == "ИБС155" and registry.normalize_code("СА432-23") == "СА432"
    assert registry.normalize_code("ИСПоз242д") == "ИСПоз242д"


def test_student_in_other_group_is_transferred_and_absent_one_is_deleted(seeded, db, tmp_path):
    old = digital_group(db, "ИИ112-26", 1, [("Иванов", "Иван", None), ("Ушедший", "Студент", None)])
    digital_group(db, "ИИ122-26", 1, [("Петров", "Пётр", None)])
    path = make_registry(tmp_path, [
        ("Иванов Иван", "Обучается", "ИИ122-26", DIGITAL, 1),
        ("Петров Пётр", "Обучается", "ИИ122-26", DIGITAL, 1),
    ])

    stats = registry.run(path, apply=True, today=TODAY)

    db.expire_all()
    ivanov = db.query(Student).filter_by(last_name="Иванов").one()
    assert ivanov.study_group.code == "ИИ122"
    closed = db.query(StudentGroupMembership).filter_by(student_id=ivanov.id, study_group_id=old.id).one()
    assert closed.end_date == TODAY - datetime.timedelta(days=1)
    assert db.query(Student).filter_by(last_name="Ушедший").count() == 0
    assert stats["студентов переведено"] == 1 and stats["студентов удалено (нет в реестре)"] == 1
    assert db.query(Student).count() == 2


def test_group_without_active_students_is_hidden(seeded, db, tmp_path):
    digital_group(db, "ОЛД111", 1, [("Ушедший", "Студент", None)])
    path = make_registry(tmp_path, [("Иванов Иван", "Обучается", "ИИ112-26", DIGITAL, 1)])

    registry.run(path, apply=True, today=TODAY)

    db.expire_all()
    assert db.query(StudyGroup).filter_by(code="ОЛД111").one().is_active is False
    assert db.query(StudyGroup).filter_by(code="ИИ112").one().is_active is True


def test_returning_student_is_restored_not_duplicated(seeded, db, tmp_path):
    digital_group(db, "ИИ112-26", 1, [("Иванов", "Иван", None)])
    student = db.query(Student).one()
    student.status, student.left_at = StudentStatus.EXPELLED, datetime.date(2026, 9, 15)
    db.commit()
    path = make_registry(tmp_path, [("Иванов Иван", "Обучается", "ИИ112-26", DIGITAL, 1)])

    registry.run(path, apply=True, today=TODAY)

    db.expire_all()
    student = db.query(Student).one()
    assert student.status == StudentStatus.STUDYING and student.left_at is None


@pytest.mark.parametrize("people, message", [
    ([("Иванов Иван", "Обучается", "Г1", "город Москва, улица Неизвестная, дом 1", 1)], "неизвестный адрес"),
    ([("Иванов Иван", "Отчислен", "Г1", DIGITAL, 1)], "неизвестный статус"),
    ([("Иванов", "Обучается", "Г1", DIGITAL, 1)], "меньше двух слов"),
    ([("Иванов Иван", "Обучается", "Г1", DIGITAL, 1), ("Иванов Иван", "Обучается", "Г1", DIGITAL, 1)], "Дубль"),
    ([("Иванов Иван", "Обучается", "Г1", DIGITAL, 1), ("Петров Пётр", "Обучается", "Г1", CYBER, 1)], "разными отделениями"),
])
def test_bad_registry_is_rejected_before_any_change(seeded, db, tmp_path, people, message):
    path = make_registry(tmp_path, people)

    with pytest.raises(RuntimeError, match=message):
        registry.run(path, apply=True, today=TODAY)

    assert db.query(Student).count() == 0


def test_absent_student_is_deleted_with_marks_and_audit_names(seeded, db, admin_headers, tmp_path):
    group = digital_group(db, "ИИ112-26", 1, [("Иванов", "Иван", None), ("Ушедший", "Студент", None)])
    gone = db.query(Student).filter_by(last_name="Ушедший").one()
    admin = db.query(User).filter_by(username="admin").one()
    code = db.query(MarkCode).first()
    db.add(AttendanceMark(student_id=gone.id, date=datetime.date(2026, 9, 10), mark_code_id=code.id,
                          comment="Ушедший заболел", created_by_user_id=admin.id))
    db.add(AuditLog(user_id=admin.id, action="student.create", entity_type="student",
                    entity_id=str(gone.id), new_value="Ушедший Студент"))
    db.commit()
    gone_id = gone.id
    path = make_registry(tmp_path, [("Иванов Иван", "Обучается", "ИИ112-26", DIGITAL, 1)])

    stats = registry.run(path, apply=True, today=TODAY)

    db.expire_all()
    assert db.get(Student, gone_id) is None
    assert db.query(AttendanceMark).count() == 0
    assert db.query(StudentGroupMembership).filter_by(student_id=gone_id).count() == 0
    assert db.query(AuditLog).filter_by(entity_type="student", entity_id=str(gone_id)).one().new_value == "[обезличено]"
    assert stats["отметок посещаемости удалено"] == 1
    assert db.get(StudyGroup, group.id).is_active is True


def test_guard_stops_a_file_that_would_delete_too_much(seeded, db, tmp_path):
    names = [(f"Студент{i:02d}", "Тест", None) for i in range(20)]
    digital_group(db, "ИИ112-26", 1, names)
    path = make_registry(tmp_path, [(f"Студент{i:02d} Тест", "Обучается", "ИИ112-26", DIGITAL, 1) for i in range(5)])

    with pytest.raises(RuntimeError, match="15 из 20"):
        registry.run(path, apply=True, today=TODAY)
    db.expire_all()
    assert db.query(Student).count() == 20  # ничего не записано

    stats = registry.run(path, apply=True, today=TODAY, force_delete=True)
    assert stats["студентов удалено (нет в реестре)"] == 15
    # предел можно поднять и без «force»
    digital_group(db, "ИИ122-26", 1, [(f"Другой{i}", "Тест", None) for i in range(20)])
    path2 = make_registry(tmp_path, [(f"Студент{i:02d} Тест", "Обучается", "ИИ112-26", DIGITAL, 1) for i in range(5)])
    stats = registry.run(path2, apply=False, today=TODAY, max_delete_percent=90)
    assert stats["студентов удалено (нет в реестре)"] == 20


def test_extra_addresses_enrolled_date_and_report_file(seeded, db, tmp_path):
    import json
    addresses = tmp_path / "addresses.json"
    addresses.write_text(json.dumps({"город Москва, улица Новая, дом 1": "Новое отделение"}, ensure_ascii=False), encoding="utf-8")
    path = make_registry(tmp_path, [("Новый Студент", "Обучается", "НО111-26", "город Москва, улица Новая, дом 1", 1)])
    report = tmp_path / "report.txt"

    registry.run(path, apply=True, today=TODAY, enrolled_at=datetime.date(2027, 9, 1),
                 address_map_file=str(addresses), report=str(report))

    assert db.query(StudyGroup).filter_by(code="НО111").one().department.name == "Новое отделение"
    assert db.query(Student).one().enrolled_at == datetime.date(2027, 9, 1)
    text = report.read_text(encoding="utf-8")
    assert "ЗАПИСЬ" in text and "студентов создано: 1" in text


def test_bad_address_map_file_is_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('["не объект"]', encoding="utf-8")
    with pytest.raises(RuntimeError, match="нужен JSON-объект"):
        registry.load_address_map(str(bad))
