"""Password hashing (bcrypt) — no plaintext ever stored."""
from __future__ import annotations

import bcrypt

# bcrypt has a 72-byte input limit; encode + truncate defensively.
_MAX = 72

# Cost factor 10 (OWASP's recommended floor for bcrypt) instead of the
# library default of 12: registration/login pay this cost synchronously
# (hash on signup, verify on login), and 12 measured ~370ms per operation
# here vs ~90ms at 10 — the dominant cost in both endpoints' response time.
# Backward-compatible: bcrypt embeds the cost factor in the hash string
# itself, so existing hashes keep verifying at whatever cost they were
# created with; only newly-created hashes use the lower cost.
_BCRYPT_ROUNDS = 10


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:_MAX]
    return bcrypt.hashpw(pw, bcrypt.gensalt(_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:_MAX], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
