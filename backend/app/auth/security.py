"""Password hashing (bcrypt) — no plaintext ever stored."""
from __future__ import annotations

import bcrypt

# bcrypt has a 72-byte input limit; encode + truncate defensively.
_MAX = 72


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:_MAX]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:_MAX], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
