from app.models import CuratorAssignment, Department, MarkCode, Role, Student, StudyGroup, User

VACANT_GROUPS = {"ИИ132", "СА332", "ИСП452д"}


def test_seed_creates_reference_data(seeded, db):
    assert db.query(Role).count() == 5
    assert db.query(MarkCode).count() == 8
    assert db.query(Department).count() == 1
    assert db.query(Department).one().name == "Диджитал"
    assert db.query(User).filter(User.username == "admin").count() == 1


def test_seed_is_idempotent(seeded, db):
    import scripts.seed as seed_script

    seed_script.run()
    assert db.query(Role).count() == 5
    assert db.query(MarkCode).count() == 8
    assert db.query(Department).count() == 1


def test_import_creates_real_dataset(imported, db):
    assert db.query(StudyGroup).count() == 44
    assert db.query(Student).count() == 989

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    assert db.query(User).filter(User.role_id == curator_role.id).count() == 24

    assert db.query(CuratorAssignment).count() == 41  # 44 групп - 3 вакансии

    vacant = {
        g.code
        for g in db.query(StudyGroup).all()
        if not db.query(CuratorAssignment).filter(CuratorAssignment.study_group_id == g.id).first()
    }
    assert vacant == VACANT_GROUPS


def test_import_is_idempotent(imported, db):
    import scripts.import_source_data as import_script

    import_script.run()
    assert db.query(StudyGroup).count() == 44
    assert db.query(Student).count() == 989
    assert db.query(CuratorAssignment).count() == 41


def test_curator_names_normalized_no_nbsp(imported, db):
    """Регрессия на дефект исходных таблиц: неразрывный пробел в ФИО куратора."""
    for user in db.query(User).all():
        assert "\xa0" not in user.full_name
