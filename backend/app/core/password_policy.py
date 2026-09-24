"""Единая политика паролей — раньше минимальная длина была 8 в одном месте
и не проверялась вовсе в другом (одноразовые приглашения), плюс ничто не
мешало поставить пароль, совпадающий с логином, или один из самых частых
паролей (см. TODO.md 2)."""

MIN_PASSWORD_LENGTH = 10

# Компактный список самых частых паролей (достаточно, чтобы отсечь
# откровенно тривиальные — не замена полноценной проверки по словарю
# скомпрометированных паролей, но лучше, чем ничего).
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789",
    "1234567890", "qwerty123", "qwertyuiop", "111111111", "administrator",
    "letmeinnow", "welcome123", "iloveyou1", "1q2w3e4r5t", "qazwsxedc",
    "abcdefgh1", "admin12345", "changeme1", "temppass1",
}


def validate_password_strength(password: str, username: str | None = None) -> None:
    """Бросает ValueError с понятным текстом, если пароль не годится."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
    if password.lower() in _COMMON_PASSWORDS:
        raise ValueError("Этот пароль слишком часто встречается — выберите другой")
    if username and password.lower() == username.lower():
        raise ValueError("Пароль не должен совпадать с логином")
