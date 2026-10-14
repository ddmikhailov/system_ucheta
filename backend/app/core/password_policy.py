"""Единая политика паролей.

Раньше требовались только длина от 10 символов и несовпадение с логином, а
чёрный список состоял из двух десятков паролей — «Kurator2026», «Qwerty12345»
и подобные проходили. Теперь пароль обязан содержать строчную и заглавную
букву, цифру и спецсимвол, не может включать последовательности (abc, 123,
qwer, йцук), повторы (aaa), логин или фамилию/имя и не должен быть одним из
распространённых паролей — в том числе с цифрами/символами по краям
(«Password2026!») и заменой букв похожими символами («P@ssw0rd»).

Те же требования (кроме словаря) показывает интерфейс — frontend/src/constants/password.ts;
длину сверяет tests/test_frontend_roles_contract.py.
"""

import re

MIN_PASSWORD_LENGTH = 10
# Верхняя граница — чтобы хэширование многомегабайтной «строки» не нагружало сервер.
MAX_PASSWORD_LENGTH = 128
# Минимум разных символов: «Aa1!Aa1!Aa1!» формально проходит остальные правила.
MIN_DISTINCT_CHARS = 6

# С какой длины запрещены последовательности: по алфавиту/цифрам — от 3 символов
# (abc, 123, 987, абв), по раскладке клавиатуры — от 4 (qwer, asdf, йцук, 1qaz):
# на 3 символах раскладка ловит слишком много обычных слогов («ert», «тан»).
SEQUENCE_LENGTH = 3
KEYBOARD_SEQUENCE_LENGTH = 4
# Один символ подряд — от 3 раз (aaa, 111, !!!).
REPEAT_LENGTH = 3

_ALPHABET_SEQUENCES = (
    "abcdefghijklmnopqrstuvwxyz",
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "абвгдежзийклмнопрстуфхцчшщъыьэюя",
    "0123456789",
)
_KEYBOARD_SEQUENCES = (
    "1234567890-=",
    "qwertyuiop[]",
    "asdfghjkl;'",
    "zxcvbnm,./",
    "йцукенгшщзхъ",
    "фывапролджэ",
    "ячсмитьбю.",
    "1qaz2wsx3edc4rfv5tgb6yhn7ujm8ik,9ol.0p;/",
    "qazwsxedcrfvtgbyhnujmikolp",
    "!@#$%^&*()_+",
)

# Замены букв похожими символами (P@ssw0rd → password). Учитываются только
# внутри «слова» — между первой и последней буквой; цифры и знаки по краям
# («Password2026!») просто отбрасываются.
_LOOKALIKES = str.maketrans({"@": "a", "4": "a", "0": "o", "1": "i", "!": "i", "3": "e", "$": "s", "5": "s", "7": "t", "8": "b"})

# Буквенная основа самых распространённых паролей (по публичным спискам утечек,
# включая русскоязычные), а также слова, очевидные для нашей платформы. Пароль
# отклоняется, если после отбрасывания цифр и символов от него остаётся одно из этих слов.
_COMMON_WORDS = frozenset("""
password passw pass passwd pasword parol changeme temppass admin administrator root user guest test tester login logon
welcome letmein iloveyou loveyou love lovely hello hellokitty secret qwerty qwertyuiop qwertz azerty
asdf asdfgh asdfghjkl zxcvbn zxcvbnm qazwsx qazwsxedc qweasd qweasdzxc zaq zaqxsw
monkey dragon master shadow superman batman spiderman football baseball soccer hockey sunshine princess
trustno whatever freedom starwars computer internet killer summer winter spring autumn flower charlie
matrix ranger buster tigger cookie pepper ginger banana orange apple chocolate cheese family friend
friends forever angel daniel michael jordan thomas robert jennifer jessica ashley nicole
maxim maksim natasha nikita marina andrey andrei alexander alexandr aleksandr sasha dima vova irina olga
svetlana tatyana tanya katya ekaterina anastasia nastya dasha masha maria elena lena sergey sergei
ivan ivanov artem denis pavel roman vladimir
kait kurator curator college kolledzh student teacher uchitel school shkola privet lubov lyubov
solnce kotik mama papa moskva moscow russia rossiya zenit spartak
gfhjkm ghbdtn rehfnjh cnelktyn vfvf gfgf
пароль парольчик админ администратор логин привет любовь люблю солнце солнышко котик котёнок
мама папа москва россия зенит спартак студент куратор колледж каит учитель школа
наташа марина саша дима вова ирина ольга света светлана таня катя настя даша маша лена
сергей иван андрей максим никита артём денис павел роман владимир
""".split())

# Подстроки, которые не допускаются нигде в пароле, даже внутри длинной фразы.
_FORBIDDEN_PARTS = (
    "password", "passwd", "parol", "qwerty", "admin", "letmein", "iloveyou", "welcome",
    "kurator", "curator", "kait", "gfhjkm", "пароль", "админ", "куратор", "каит", "йцукен",
)

# Целиком распространённые пароли, у которых нет буквенной основы для проверки выше.
_COMMON_PASSWORDS = frozenset("""
1q2w3e4r 1q2w3e4r5t 1q2w3e4r5t6y 1qaz2wsx 1qaz2wsx3edc zaq12wsx q1w2e3r4 q1w2e3r4t5 a1b2c3d4
1a2b3c4d 123qwe 123qweasd qwe123 abc123 abc12345
""".split())


def _sequence_in(text: str, sequences: tuple[str, ...], length: int) -> str | None:
    for i in range(len(text) - length + 1):
        chunk = text[i:i + length]
        for seq in sequences:
            if chunk in seq or chunk[::-1] in seq:
                return chunk
    return None


def _letter_core(lower: str) -> str:
    """Буквенная основа пароля: похожие символы внутри слова заменены буквами,
    всё небуквенное отброшено («P@ssw0rd2026!» → «password»)."""
    letters = [i for i, c in enumerate(lower) if c.isalpha()]
    if not letters:
        return ""
    first, last = letters[0], letters[-1]
    inner = lower[first:last + 1].translate(_LOOKALIKES)
    return "".join(c for c in inner if c.isalpha())


def password_problems(password: str, username: str | None = None, full_name: str | None = None) -> list[str]:
    """Все нарушенные требования — списком понятных фраз (пустой список — пароль подходит)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return [f"пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"]
    if len(password) > MAX_PASSWORD_LENGTH:
        return [f"пароль должен быть не длиннее {MAX_PASSWORD_LENGTH} символов"]

    problems = []
    missing = []
    if not any(c.islower() for c in password):
        missing.append("строчную букву")
    if not any(c.isupper() for c in password):
        missing.append("заглавную букву")
    if not any(c.isdigit() for c in password):
        missing.append("цифру")
    if not any(not c.isalnum() and not c.isspace() for c in password):
        missing.append("спецсимвол (например ! # $ % & * ?)")
    if missing:
        problems.append("добавьте " + ", ".join(missing))

    lower = password.lower()
    if len(set(lower)) < MIN_DISTINCT_CHARS:
        problems.append(f"используйте не меньше {MIN_DISTINCT_CHARS} разных символов")
    if re.search(r"(.)\1{%d,}" % (REPEAT_LENGTH - 1), lower):
        problems.append(f"один и тот же символ не должен повторяться {REPEAT_LENGTH} раза подряд")
    sequence = _sequence_in(lower, _ALPHABET_SEQUENCES, SEQUENCE_LENGTH) or _sequence_in(
        lower, _KEYBOARD_SEQUENCES, KEYBOARD_SEQUENCE_LENGTH
    )
    if sequence:
        problems.append(f"уберите последовательность «{sequence}» — подряд идущие буквы, цифры или клавиши")

    core = _letter_core(lower)
    if (
        lower in _COMMON_PASSWORDS
        or core in _COMMON_WORDS
        or any(part in lower or part in core for part in _FORBIDDEN_PARTS)
    ):
        problems.append("это слишком распространённый пароль — его легко подобрать")

    if username and len(username) >= 3 and username.lower() in lower:
        problems.append("пароль не должен содержать логин")
    if full_name:
        for part in re.split(r"[\s.\-]+", full_name.lower()):
            if len(part) >= 3 and (part in lower or part in core):
                problems.append("пароль не должен содержать фамилию, имя или отчество")
                break
    return problems


def validate_password_strength(password: str, username: str | None = None, full_name: str | None = None) -> None:
    """Бросает ValueError с понятным текстом, если пароль не годится."""
    problems = password_problems(password, username, full_name)
    if problems:
        text = "; ".join(problems)
        raise ValueError(f"Пароль не подходит: {text}")
