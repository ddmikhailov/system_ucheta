"""Шифрование особых полей досье в БД (Fernet: AES-128-CBC + HMAC).

Ключ — DOSSIER_ENCRYPTION_KEY. Без ключа ничего не шифруем и не читаем:
молча писать открытым текстом особые данные нельзя, поэтому — исключение,
которое API превращает в 503 только для особых полей."""
import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionUnavailable(Exception):
    pass


def _fernet() -> Fernet:
    key = get_settings().dossier_encryption_key
    if not key:
        raise EncryptionUnavailable("Не задан DOSSIER_ENCRYPTION_KEY")
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise EncryptionUnavailable("DOSSIER_ENCRYPTION_KEY некорректен") from exc


def is_available() -> bool:
    try:
        _fernet()
    except EncryptionUnavailable:
        return False
    return True


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()


def decrypt_json(token: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken as exc:
        raise EncryptionUnavailable("Не удалось расшифровать данные — ключ изменился?") from exc
