"""Скрытие групп со строчной «о» в коде."""
import scripts.hide_groups as hide_groups
from app.models import Department, StudyGroup


def make_groups(db, codes):
    department = Department(name="Тест")
    db.add(department)
    db.flush()
    for code in codes:
        db.add(StudyGroup(code=code, course=1, department_id=department.id))
    db.commit()


def active_codes(db):
    db.expire_all()
    return {g.code for g in db.query(StudyGroup).filter(StudyGroup.is_active.is_(True))}


def test_hides_only_groups_with_lowercase_o(seeded, db):
    make_groups(db, ["ИИ112", "ИСПо212", "ГДоз226д", "РУо112", "СА332"])

    stats = hide_groups.run(apply=True)

    assert active_codes(db) == {"ИИ112", "СА332"}  # группа без куратора не скрывается
    assert stats == {"скрыто (строчная «о» в коде)": 3}


def test_uppercase_o_and_latin_o_do_not_hide_a_group(seeded, db):
    make_groups(db, ["ОИС122", "ИСПo212"])  # заглавная кириллическая «О» и латинская «o»

    hide_groups.run(apply=True)

    assert active_codes(db) == {"ОИС122", "ИСПo212"}


def test_dry_run_and_second_run_change_nothing(seeded, db):
    make_groups(db, ["ИИ112", "ИСПо212"])

    hide_groups.run(apply=False)
    assert active_codes(db) == {"ИИ112", "ИСПо212"}

    hide_groups.run(apply=True)
    stats = hide_groups.run(apply=True)

    assert active_codes(db) == {"ИИ112"}
    assert stats == {"скрыто (строчная «о» в коде)": 0}
