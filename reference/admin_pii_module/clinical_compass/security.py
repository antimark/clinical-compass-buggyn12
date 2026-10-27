"""Storage encryption and non-reversible password hashes; no key in SQLite."""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
from cryptography.fernet import Fernet


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must have at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        tag, b64salt, b64digest = stored.split("$")
        if tag != "scrypt":
            return False
        salt = base64.b64decode(b64salt, validate=True)
        digest = base64.b64decode(b64digest, validate=True)
        if len(salt) != 16 or len(digest) != 32:
            return False
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False


class PiiCipher:
    def __init__(self, key: str | bytes):
        self.fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        return self.fernet.decrypt(value.encode("ascii")).decode("utf-8")
