"""Политика сложности паролей: классы символов, последовательности, повторы,
распространённые пароли, логин и ФИО; генератор временных паролей; слабый
пароль, заданный до ужесточения, при входе требует смены."""

import pytest

from app.core.password_policy import MAX_PASSWORD_LENGTH, password_problems, validate_password_strength
from app.core.security import hash_password
from app.models import AuditLog
from app.services.password_service import generate_temporary_password
from tests.conftest import CURATOR_PASSWORD

GOOD = "Vz8#kQm2Lp"


def _problems(password, username=None, full_name=None):
    return " | ".join(password_problems(password, username, full_name))


def test_strong_passwords_pass():
    for password in (GOOD, "Hk3$Wp7Nv!", "Тигр9Лес!Ч", "Kot5Lapa!Xm"):
        assert password_problems(password) == [], password


@pytest.mark.parametrize("password, missing", [
    ("vz8#kqm2lp", "заглавную букву"),
    ("VZ8#KQM2LP", "строчную букву"),
    ("Vzx#kQmbLp", "цифру"),
    ("Vz8XkQm2Lp", "спецсимвол"),
    ("Vz8 kQm2Lp", "спецсимвол"),  # пробел спецсимволом не считается
])
def test_every_character_class_is_required(password, missing):
    assert missing in _problems(password)


def test_missing_classes_are_listed_together():
    assert "добавьте заглавную букву, цифру, спецсимвол" in _problems("onlylowercase")


def test_length_limits():
    assert "не короче 10" in _problems("Vz8#kQm2L")
    assert "не длиннее" in _problems("Vz8#kQm2Lp" * (MAX_PASSWORD_LENGTH // 10 + 1))


@pytest.mark.parametrize("password, sequence", [
    ("Vz123#kQmL", "123"),
    ("Vz987#kQmL", "987"),
    ("Abc8#kQm2L", "abc"),
    ("Vz8#kQmZyx", "zyx"),
    ("Абв8#кЮм2Л", "абв"),
    ("Qwer8#kZm2", "qwer"),
    ("Vz8#Asdf2L", "asdf"),
    ("Йцук8#Zm2L", "йцук"),
    ("Vz1qaz#Lm8", "1qaz"),
])
def test_sequences_are_rejected(password, sequence):
    assert f"«{sequence}»" in _problems(password)


@pytest.mark.parametrize("password", ["Vz8#kkkQm2L", "Vz8#kQ222mL", "Vz8#!!!Qm2L"])
def test_three_identical_characters_in_a_row_are_rejected(password):
    assert "3 раза подряд" in _problems(password)


def test_too_few_distinct_characters():
    assert "разных символов" in _problems("Aa1!Aa1!Aa1!")


@pytest.mark.parametrize("password", [
    "Password2026!",   # словарное слово с цифрами и символом по краям
    "P@ssw0rd2026!",   # с заменой букв похожими символами
    "Kurator2026!",    # очевидное для платформы
    "Monkey2026!",
    "Солнце2026!",
    "Gfhjkm2026!",     # «пароль», набранный в английской раскладке
    "MyAdmin#2026",    # запрещённая подстрока внутри фразы
    "1q2w3e4r5t",
])
def test_common_passwords_are_rejected(password):
    assert "распространённый" in _problems(password)


def test_username_and_full_name_are_rejected():
    assert "логин" in _problems("Ivanova7#Xq", username="ivanova")
    assert "фамилию" in _problems("Анна7#Xqzw", full_name="Иванова Анна Сергеевна")
    # Короткие части имени (меньше 3 букв) не мешают.
    assert password_problems(GOOD, username="vz", full_name="Ли Ян") == []


def test_validate_raises_with_all_problems():
    with pytest.raises(ValueError, match="Пароль не подходит: .*заглавную.*«abc»"):
        validate_password_strength("abc123xyz9")


def test_generated_passwords_satisfy_the_policy():
    passwords = {generate_temporary_password() for _ in range(300)}
    assert len(passwords) == 300
    for password in passwords:
        assert password_problems(password) == [], password
        assert password[0].isalpha()  # не начинается с символа формулы Excel
        assert not set(password) & set("Il1O0=+-@")


# --- API ---------------------------------------------------------------------

def test_change_password_rejects_weak_password_with_reason(client, curator_headers):
    r = client.post("/auth/change-password", headers=curator_headers,
                    json={"current_password": CURATOR_PASSWORD, "new_password": "Password2026!"})
    assert r.status_code == 400
    assert "распространённый" in r.json()["detail"]


def test_change_password_rejects_full_name(client, curator_headers, curator_user):
    surname = curator_user.full_name.split()[0]
    r = client.post("/auth/change-password", headers=curator_headers,
                    json={"current_password": CURATOR_PASSWORD, "new_password": f"{surname}#8Qz"})
    assert r.status_code == 400
    assert "фамилию" in r.json()["detail"]


def test_admin_custom_password_follows_the_policy(client, admin_headers, curator_user):
    weak = client.post(f"/admin/users/{curator_user.id}/set-password", headers=admin_headers,
                       json={"password": "Qwerty12345"})
    assert weak.status_code == 400
    assert "спецсимвол" in weak.json()["detail"]

    ok = client.post(f"/admin/users/{curator_user.id}/set-password", headers=admin_headers, json={"password": GOOD})
    assert ok.status_code == 200


def test_generated_admin_password_follows_the_policy(client, admin_headers, curator_user):
    r = client.post(f"/admin/users/{curator_user.id}/set-password", headers=admin_headers, json={})
    assert r.status_code == 200
    assert password_problems(r.json()["password"]) == []


def test_weak_password_set_before_the_policy_forces_a_change_on_login(client, db, curator_user):
    curator_user.password_hash = hash_password("kurator2020")
    db.commit()

    r = client.post("/auth/login", json={"username": curator_user.username, "password": "kurator2020"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/auth/me", headers=headers).json()["must_change_password"] is True
    assert client.get("/curator/groups", headers=headers).status_code == 403  # дальше — только после смены

    db.expire_all()
    assert db.query(AuditLog).filter_by(action="password.weak_on_login", entity_id=str(curator_user.id)).count() == 1

    changed = client.post("/auth/change-password", headers=headers, json={"new_password": GOOD})
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False


def test_strong_password_does_not_force_a_change_on_login(client, curator_headers):
    assert client.get("/auth/me", headers=curator_headers).json()["must_change_password"] is False
