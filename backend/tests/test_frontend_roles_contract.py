"""Контракт «фронтенд ↔ бэкенд» по ролям: списки в frontend/src/constants/roles.ts должны совпадать
с теми, что реально применяет бэкенд. Раньше такие списки жили в десятке мест и расходились при
каждом изменении прав (например, тьютор из «админа колледжа» стал «админом отделения» — интерфейс
об этом не узнал)."""
import re
from pathlib import Path

import pytest

from app.core import policies, roles
from app.models import RoleCode
from app.services import task_service

ROLES_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "constants" / "roles.ts"


def _parse() -> dict[str, set[str]]:
    """Достаёт из roles.ts константы вида `export const NAME: Roles = [ROLE.A, ...OTHER, ...]`."""
    text = ROLES_TS.read_text(encoding="utf-8")
    role_map = dict(re.findall(r"(\w+):\s*\"(\w+)\"", text.split("} as const;")[0].split("export const ROLE = {")[1]))
    groups: dict[str, set[str]] = {}
    for name, body in re.findall(r"export const (\w+): Roles = \[(.*?)\];", text, flags=re.S):
        members: set[str] = set()
        for token in (t.strip() for t in body.split(",") if t.strip()):
            if token.startswith("..."):
                members |= groups[token[3:]]
            else:
                members.add(role_map[token.split(".")[1]])
        groups[name] = members
    groups["__roles__"] = set(role_map.values())
    return groups


@pytest.fixture(scope="module")
def ts():
    return _parse()


def _values(roles_iterable) -> set[str]:
    return {r.value if isinstance(r, RoleCode) else r for r in roles_iterable}


def test_the_role_list_matches_the_backend_enum(ts):
    assert ts["__roles__"] == {r.value for r in RoleCode}


@pytest.mark.parametrize("ts_name,backend", [
    ("DEPARTMENT_SCOPED_ROLES", roles.DEPARTMENT_SCOPED_ROLES),
    ("DOSSIER_STAFF_ROLES", roles.DOSSIER_STAFF_ROLES),
    ("COLLEGE_WIDE_ROLES", roles.COLLEGE_WIDE_ROLES),
    ("TASK_MANAGER_ROLES", task_service.TASK_MANAGER_ROLES),
    ("CURATOR_CAPABLE_ROLES", policies.CURATOR_CAPABLE_ROLES),
    ("DEPARTMENT_REQUIRED_ROLES", policies.DEPARTMENT_REQUIRED_ROLES),
])
def test_role_groups_match_the_backend(ts, ts_name, backend):
    assert ts[ts_name] == _values(backend), f"{ts_name} разошлись с бэкендом"


def _user(role: str):
    from app.models import Role, User

    return User(username="x", full_name="x", role=Role(code=role, name=role))


def test_assignable_roles_match_the_policies(ts):
    """assignableRoles() из roles.ts: админ — любые, зав. отделением — рабочие + зав. отделением, тьютор — рабочие."""

    def can_assign(actor_role: str) -> set[str]:
        allowed = set()
        for role in RoleCode:
            try:
                policies.assert_can_assign_role(_user(actor_role), role.value)
                allowed.add(role.value)
            except Exception:
                pass
        return allowed

    working = ts["TEACHER_ROLES"] | ts["DOSSIER_STAFF_ROLES"]
    assert can_assign("admin") == ts["__roles__"]
    assert can_assign("dept_head") == working | {"dept_head"}
    assert can_assign("tutor") == working
    for other in ("curator", "deputy_curator", "edu_department", "social_pedagogue", "psychologist"):
        assert can_assign(other) == set()


def test_access_groups_follow_the_backend_dependencies(ts):
    """Кого реально пускают зависимости эндпоинтов — по поведению, а не по тексту: роль либо проходит, либо 403."""
    from fastapi import HTTPException

    from app.api import deps

    def allowed(dependency) -> set[str]:
        result = set()
        for role in RoleCode:
            try:
                dependency(_user(role.value))
                result.add(role.value)
            except HTTPException:
                pass
        return result

    assert allowed(deps.require_management) == ts["MANAGEMENT_ROLES"]
    assert allowed(deps.require_viewer) == ts["VIEWER_ROLES"]
    assert allowed(deps.require_structure_editor) == ts["STRUCTURE_EDITOR_ROLES"]
    assert allowed(deps.require_reference_editor) == ts["REFERENCE_EDITOR_ROLES"]

    from app.api.routers import attendance_changes

    assert allowed(attendance_changes.require_reviewer) == ts["JOURNAL_REVIEWER_ROLES"]


def test_force_delete_group_roles_match_the_backend(ts):
    """Кому интерфейс показывает «Удалить группу навсегда…» — те же, кого пускает бэкенд."""
    assert ts["FORCE_DELETE_GROUP_ROLES"] == _values(policies.ELEVATED_ROLES)


def test_min_password_length_matches_the_frontend():
    """Форма смены пароля и форма «Задать свой пароль» проверяют ту же длину, что бэкенд (раньше вторая — 8 вместо 10)."""
    from app.core.password_policy import MIN_PASSWORD_LENGTH

    text = (ROLES_TS.parent / "password.ts").read_text(encoding="utf-8")
    assert int(re.search(r"MIN_PASSWORD_LENGTH = (\d+)", text).group(1)) == MIN_PASSWORD_LENGTH
