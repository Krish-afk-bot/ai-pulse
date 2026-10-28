import pytest

from app import seed
from tests.conftest import login


@pytest.fixture()
def demo_client(client):
    """Re-seed with the demo assessments included, then reuse the test client."""
    seed.run()
    return client


def _dashboard(client, email, org_name):
    headers, data = login(client, email, org_name)
    org_id = next(o["org_id"] for o in data["organizations"] if o["org_name"] == org_name)
    response = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_northwind_pools_all_small_departments(demo_client):
    data = _dashboard(demo_client, "asha@northwind.test", "Northwind Logistics")

    # No team reaches 5 on its own, so only the pooled row is left.
    assert [row["department"] for row in data["departments"]] == ["Other teams"]
    other = data["departments"][0]
    assert other["is_group"] is True
    assert other["responded"] == 10

    flags = {flag for flag, _ in data["top_risks"]}
    assert "unreviewed_output" in flags  # 5 people have it
    assert "customer_data_shared" not in flags  # only 3 people have it


def test_priya_finishing_her_diagnostic_releases_support(demo_client):
    headers, _ = login(demo_client, "priya@northwind.test", "Northwind Logistics")
    questions = demo_client.get("/diagnostic/questions", headers=headers).json()
    # Priya's open answer is already stored; submit the missing multiple-choice ones.
    answers = [
        {"question_id": question["id"], "answer": question["options"][0]}
        for question in questions
        if question["type"] == "mcq"
    ]
    submit = demo_client.post("/diagnostic/submit", headers=headers, json={"answers": answers})
    assert submit.status_code == 200

    data = _dashboard(demo_client, "asha@northwind.test", "Northwind Logistics")
    rows = {row["department"]: row for row in data["departments"]}
    assert rows["Support"]["responded"] == 5
    assert rows["Support"]["is_group"] is False
    assert rows["Other teams"]["responded"] == 6


def test_bluepeak_has_no_releasable_group(demo_client):
    data = _dashboard(demo_client, "meera@bluepeak.test", "Bluepeak Retail")
    assert data["departments"] == []
    assert data["top_risks"] == []
