import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from .config import SECRET_KEY, TOKEN_HOURS
from .db import get_db
from . import models


# scrypt is a slow, memory-hard hash, so a stolen password hash is expensive to
# brute-force. The legacy SHA-256 fallback stays so people created before this
# change can still log in; the login route upgrades them to scrypt afterwards.
# N is the cost: tests lower SCRYPT_N to hash seeded users quickly.
_SCRYPT_N = int(os.getenv("SCRYPT_N", "16384"))
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_BYTES
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${key.hex()}"


def _verify_legacy(password: str, stored: str) -> bool:
    if len(stored) != 64:
        return False
    try:
        int(stored, 16)
        return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)
    except (ValueError, TypeError):
        return False


def verify_password(password: str, stored: str) -> bool:
    if not isinstance(stored, str):
        return False
    if not stored.startswith("scrypt$"):
        return _verify_legacy(password, stored)
    try:
        _, n, r, p, salt_hex, hash_hex = stored.split("$")
        key = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=_KEY_BYTES,
        )
        return hmac.compare_digest(key.hex(), hash_hex)
    except (ValueError, TypeError, OverflowError):
        return False


def needs_rehash(stored: str) -> bool:
    """True for legacy SHA-256 hashes or scrypt hashes with old parameters."""
    if not isinstance(stored, str) or not stored.startswith("scrypt$"):
        return True
    try:
        _, n, r, p, _salt, _hash = stored.split("$")
        return (int(n), int(r), int(p)) != (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    except (ValueError, TypeError):
        return True


def make_token(user_id: int, org_id: int | None = None) -> str:
    payload = {
        "sub": str(user_id),
        "org": org_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _decode(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    try:
        return jwt.decode(authorization[7:], SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")


def current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> models.User:
    data = _decode(authorization)
    user = db.get(models.User, int(data["sub"]))
    if not user:
        raise HTTPException(401, "Unknown user")
    return user


def current_membership(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> models.Membership:
    """The membership for the organization selected after login."""
    data = _decode(authorization)
    if not data.get("org"):
        raise HTTPException(400, "Select an organization first")
    m = (
        db.query(models.Membership)
        .filter_by(user_id=int(data["sub"]), org_id=data["org"])
        .first()
    )
    if not m:
        raise HTTPException(403, "Not a member of this organization")
    return m
