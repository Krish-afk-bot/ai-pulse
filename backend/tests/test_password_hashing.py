import hashlib

from app.auth import hash_password, verify_password, needs_rehash
from app.db import SessionLocal
from app import models

EMAIL = "priya@northwind.test"


def _legacy_hash(password: str) -> str:
    """The old scheme: plain, unsalted SHA-256 hex. Used to test the fallback."""
    return hashlib.sha256(password.encode()).hexdigest()


def _set_password_hash(email: str, value: str) -> None:
    db = SessionLocal()
    try:
        db.query(models.User).filter_by(email=email).first().password_hash = value
        db.commit()
    finally:
        db.close()


def _read_password_hash(email: str) -> str:
    db = SessionLocal()
    try:
        return db.query(models.User).filter_by(email=email).first().password_hash
    finally:
        db.close()


def test_two_hashes_of_same_password_differ():
    # A random salt per call means the same password never produces the same hash.
    assert hash_password("pulse123") != hash_password("pulse123")


def test_correct_password_verifies_and_wrong_does_not():
    stored = hash_password("pulse123")
    assert verify_password("pulse123", stored) is True
    assert verify_password("not-the-password", stored) is False


def test_new_hash_needs_no_rehash():
    assert needs_rehash(hash_password("pulse123")) is False


def test_legacy_sha256_hash_still_verifies():
    legacy = _legacy_hash("pulse123")
    assert needs_rehash(legacy) is True
    assert verify_password("pulse123", legacy) is True
    assert verify_password("wrong", legacy) is False


def test_scrypt_hash_with_old_parameters_needs_rehash():
    old = "scrypt$8192$8$1$" + "aa" * 16 + "$" + "bb" * 32
    assert needs_rehash(old) is True


def test_malformed_stored_values_return_false():
    bad_values = ["", "not-a-hash", "scrypt$16384$8", "scrypt$x$8$1$aa$bb",
                  "scrypt$16384$8$1$zz$zz", "scrypt$16384$8$1$aa$é",
                  "scrypt$99999999999999999999$8$1$aa$bb", None]
    for bad in bad_values:
        assert verify_password("pulse123", bad) is False


def test_login_with_legacy_hash_upgrades_to_scrypt(client):
    _set_password_hash(EMAIL, _legacy_hash("pulse123"))
    r = client.post("/auth/login", json={"email": EMAIL, "password": "pulse123"})
    assert r.status_code == 200
    stored = _read_password_hash(EMAIL)
    assert stored.startswith("scrypt$")
    assert verify_password("pulse123", stored) is True


def test_failed_login_leaves_legacy_hash_unchanged(client):
    legacy = _legacy_hash("pulse123")
    _set_password_hash(EMAIL, legacy)
    r = client.post("/auth/login", json={"email": EMAIL, "password": "wrong-password"})
    assert r.status_code == 401
    assert _read_password_hash(EMAIL) == legacy
