"""Замена куратора на даты (п. 4.3 положения): заместитель с периодом «с — по»."""
import datetime

import pytest

from app.models import CuratorAssignment, InAppNotification, Role, RoleCode, StudyGroup, User
from app.models.enums import AssignmentRole
from app.services.access_service import get_curator_group_ids

D = datetime.date


@pytest.fixture()
def setup(db, imported):
    """Группа с основным куратором и второй куратор, который будет её замещать."""
    main = (
        db.query(CuratorAssignment).filter(CuratorAssignment.role_type == AssignmentRole.CURATOR)
        .order_by(CuratorAssignment.id).first()
    )
    role = db.query(Role).filter(Role.code == RoleCode.CURATOR.value).one()
    other = db.query(User).filter(User.role_id == role.id, User.id != main.user_id).order_by(User.id).first()
    group = db.get(StudyGroup, main.study_group_id)
    return {"group": group, "main": main.user, "other": other}


def _post(client, headers, setup, start, end, user=None):
    return client.post(
        "/admin/curator-assignments", headers=headers,
        json={
            "study_group_id": setup["group"].id, "user_id": (user or setup["other"]).id,
            "role_type": "deputy", "start_date": start, "end_date": end,
        },
    )


def test_substitute_has_access_only_during_period(client, admin_headers, setup, db):
    assert _post(client, admin_headers, setup, "2031-03-10", "2031-03-14").status_code == 201
    gid, other = setup["group"].id, setup["other"]
    assert gid not in get_curator_group_ids(db, other, D(2031, 3, 9))
    assert gid in get_curator_group_ids(db, other, D(2031, 3, 10))
    assert gid in get_curator_group_ids(db, other, D(2031, 3, 14))
    assert gid not in get_curator_group_ids(db, other, D(2031, 3, 15))
    # основной куратор группу не теряет
    assert gid in get_curator_group_ids(db, setup["main"], D(2031, 3, 12))


def test_substitution_does_not_end_main_curator(client, admin_headers, setup, db):
    _post(client, admin_headers, setup, "2031-03-10", "2031-03-14")
    main = (
        db.query(CuratorAssignment)
        .filter(CuratorAssignment.user_id == setup["main"].id, CuratorAssignment.study_group_id == setup["group"].id)
        .one()
    )
    assert main.end_date is None


def test_both_get_notification(client, admin_headers, setup, db):
    _post(client, admin_headers, setup, "2031-03-10", "2031-03-14")
    kinds = {
        n.user_id: n.message for n in db.query(InAppNotification).filter(InAppNotification.kind == "curator_substitution")
    }
    assert "замещаете" in kinds[setup["other"].id] and "10.03.2031 по 14.03.2031" in kinds[setup["other"].id]
    assert setup["other"].full_name in kinds[setup["main"].id]


def test_overlapping_substitution_rejected(client, admin_headers, setup, db):
    assert _post(client, admin_headers, setup, "2031-03-10", "2031-03-14").status_code == 201
    r = _post(client, admin_headers, setup, "2031-03-12", "2031-03-20")
    assert r.status_code == 400 and "уже есть заместитель" in r.json()["detail"]
    # соседний период без пересечения разрешён
    assert _post(client, admin_headers, setup, "2031-03-15", "2031-03-20").status_code == 201


def test_cannot_substitute_oneself(client, admin_headers, setup):
    r = _post(client, admin_headers, setup, "2031-03-10", "2031-03-14", user=setup["main"])
    assert r.status_code == 400


def test_end_before_start_rejected(client, admin_headers, setup):
    assert _post(client, admin_headers, setup, "2031-03-14", "2031-03-10").status_code == 400


def test_open_ended_deputy_replaces_previous(client, admin_headers, setup, db):
    """«Сменить заместителя» работает как раньше: новый без даты окончания заканчивает прежнего накануне."""
    _post(client, admin_headers, setup, "2030-01-01", None)
    assert _post(client, admin_headers, setup, "2030-02-01", None).status_code == 201
    first = db.query(CuratorAssignment).filter(
        CuratorAssignment.role_type == AssignmentRole.DEPUTY, CuratorAssignment.start_date == D(2030, 1, 1),
    ).one()
    assert first.end_date == D(2030, 1, 31)


def test_future_substitution_listed_and_cancel_deletes(client, admin_headers, setup, db):
    r = _post(client, admin_headers, setup, "2031-03-10", "2031-03-14")
    assignment_id = r.json()["id"]
    row = next(g for g in client.get("/admin/groups", headers=admin_headers).json() if g["id"] == setup["group"].id)
    assert row["deputy_assignment_id"] == assignment_id
    assert (row["deputy_start_date"], row["deputy_end_date"]) == ("2031-03-10", "2031-03-14")
    assert client.post(f"/admin/curator-assignments/{assignment_id}/end", headers=admin_headers).status_code == 200
    assert db.get(CuratorAssignment, assignment_id) is None


def test_roles_matrix(client, setup, admin_headers, dept_head_headers, curator_headers, edu_department_headers):
    """Назначает замену управление; куратор — нет."""
    assert _post(client, curator_headers, setup, "2031-03-10", "2031-03-14").status_code == 403
    assert _post(client, dept_head_headers, setup, "2031-03-10", "2031-03-14").status_code == 201
    assert _post(client, edu_department_headers, setup, "2031-04-10", "2031-04-14").status_code == 201
