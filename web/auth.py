from __future__ import annotations

from passlib.context import CryptContext
from passlib.exc import UnknownHashError

pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def is_password_hash(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith('$pbkdf2-sha256$')


def verify_password(plain_password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False

    try:
        return pwd_context.verify(plain_password, password_hash)
    except UnknownHashError:
        return False
    except Exception:
        return False