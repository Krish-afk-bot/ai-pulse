from datetime import datetime, timedelta, timezone

import jwt

from tests.conftest import login

# The secret that was committed in backend/.env (and is still in git history).
OLD_SECRET = "pulse-7f3a9c2e1b-prod"


def _forged_token(secret):
    payload = {"sub": "1", "org": 1, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_token_signed_with_old_committed_secret_is_rejected(client):
    headers = {"Authorization": f"Bearer {_forged_token(OLD_SECRET)}"}
    assert client.get("/diagnostic/questions", headers=headers).status_code == 401


def test_normal_login_token_still_works(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    assert client.get("/diagnostic/questions", headers=headers).status_code == 200
