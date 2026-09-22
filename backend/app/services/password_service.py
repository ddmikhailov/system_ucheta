import secrets
import string

# Без символов, которые визуально путаются при ручном наборе (I/l/1, O/0) —
# см. обновление 1.1: администратор диктует/печатает временный пароль
# человеку, опечатки в неоднозначных символах были причиной блокировок.
_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "Il1O0")


def generate_temporary_password(length: int = 12) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
