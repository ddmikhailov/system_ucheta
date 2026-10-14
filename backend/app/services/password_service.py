import secrets
import string

from app.core.password_policy import password_problems

# Без символов, которые визуально путаются при ручном наборе (I/l/1, O/0) —
# см. обновление 1.1: администратор диктует/печатает временный пароль
# человеку, опечатки в неоднозначных символах были причиной блокировок.
_LOWER = "".join(c for c in string.ascii_lowercase if c not in "lo")
_UPPER = "".join(c for c in string.ascii_uppercase if c not in "IO")
_DIGITS = "23456789"
# Спецсимволы, которые легко продиктовать и которые не начинают формулу в
# Excel/CSV (=, +, -, @ — сюда не входят).
_SPECIAL = "!#$%&*?"
_ALPHABET = _LOWER + _UPPER + _DIGITS + _SPECIAL


def generate_temporary_password(length: int = 14) -> str:
    """Случайный пароль, удовлетворяющий политике (все классы символов, без
    последовательностей и повторов). Начинается с буквы — так его проще
    продиктовать, и он не превращается в формулу в таблице."""
    rng = secrets.SystemRandom()
    while True:
        chars = [rng.choice(_LOWER), rng.choice(_UPPER), rng.choice(_DIGITS), rng.choice(_SPECIAL)]
        chars += [rng.choice(_ALPHABET) for _ in range(length - len(chars))]
        rng.shuffle(chars)
        if not chars[0].isalpha():
            continue
        password = "".join(chars)
        if not password_problems(password):
            return password
