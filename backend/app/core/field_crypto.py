"""Шифрование особых полей досье в БД (Fernet: AES-128-CBC + HMAC).

Ключ — DOSSIER_ENCRYPTION_KEY. Без ключа ничего не шифруем и не читаем:
молча писать открытым текстом особые данные нельзя, поэтому — исключение,
которое API превращает в 503 только для особых полей.

Смена ключа без потери данных (MultiFernet): в DOSSIER_ENCRYPTION_KEY через запятую «новый,старый». Новым
шифруется всё, что записывается, читаются данные под любым из ключей; `python -m scripts.rotate_dossier_key
--apply` перешифровывает уже сохранённое новым ключом, после чего старый из списка можно убрать
(порядок — в docs/deploy/kait20-klyuch-dosie.txt)."""
import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings


class EncryptionUnavailable(Exception):
    pass


def _keys() -> list[str]:
    return [part.strip() for part in get_settings().dossier_encryption_key.split(",") if part.strip()]


def _fernet() -> MultiFernet:
    keys = _keys()
    if not keys:
        raise EncryptionUnavailable("Не задан DOSSIER_ENCRYPTION_KEY")
    try:
        return MultiFernet([Fernet(key.encode()) for key in keys])
    except ValueError as exc:
        raise EncryptionUnavailable("DOSSIER_ENCRYPTION_KEY некорректен") from exc


def is_available() -> bool:
    try:
        _fernet()
    except EncryptionUnavailable:
        return False
    return True


def key_count() -> int:
    return len(_keys())


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()


def decrypt_json(token: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken as exc:
        raise EncryptionUnavailable("Не удалось расшифровать данные — ключ изменился?") from exc


def rotate(token: str) -> str:
    """Перешифровать сохранённое значение первым (новым) ключом; содержимое не меняется."""
    try:
        return _fernet().rotate(token.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionUnavailable("Не удалось расшифровать данные ни одним из ключей") from exc
