
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = getattr(settings, "FIELD_KEY", None)

    if not key:
        raise RuntimeError(
            "FIELD_KEY is missing from Django settings."
        )

    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            "FIELD_KEY is not a valid Fernet encryption key."
        ) from error


def encrypt(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("A valid text value is required.")

    return _fernet().encrypt(text.strip().encode())


def decrypt(blob):
    try:
        return _fernet().decrypt(bytes(blob)).decode()
    except (InvalidToken, UnicodeDecodeError, TypeError, ValueError) as error:
        raise ValueError(
            "The encrypted ID number could not be decrypted."
        ) from error


def sha256(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("A valid ID number is required.")

    normalized = text.strip().upper()

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()
