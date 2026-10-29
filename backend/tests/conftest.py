import os
import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["AI_MODE"] = "mock"
# Fixed test secret so tests never depend on a developer's local .env (and can
# prove that the old committed secret no longer signs valid tokens).
os.environ["SECRET_KEY"] = "test-secret-ai-pulse"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import seed  # noqa: E402


@pytest.fixture()
def client():
    # Tests start from a clean seed (no complete assessments); the demo
    # assessments in seed.run() are added only by test_seed_demo.py.
    seed.run(with_demo=False)
    return TestClient(app)


def login(client, email, org_name=None):
    r = client.post("/auth/login", json={"email": email, "password": "pulse123"})
    data = r.json()
    token = data["token"]
    if org_name:
        org = next(o for o in data["organizations"] if o["org_name"] == org_name)
        token = client.post("/auth/select-org", json={"org_id": org["org_id"]},
                            headers={"Authorization": f"Bearer {token}"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}, data
