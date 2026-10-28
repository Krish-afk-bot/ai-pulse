from tests.conftest import login


def test_login_lists_organizations(client):
    _, data = login(client, "ravi@consult.test")
    names = {o["org_name"] for o in data["organizations"]}
    assert names == {"Northwind Logistics", "Bluepeak Retail"}


def test_employee_sees_questions(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    r = client.get("/diagnostic/questions", headers=headers)
    assert r.status_code == 200
    assert any(q["id"] == "sup-drafts" for q in r.json())


def test_admin_dashboard(client):
    headers, data = login(client, "asha@northwind.test", "Northwind Logistics")
    org_id = data["organizations"][0]["org_id"]
    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["departments"]) == 4


def test_admin_cannot_see_other_org(client):
    headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    _, bluepeak = login(client, "meera@bluepeak.test", "Bluepeak Retail")
    other_org_id = bluepeak["organizations"][0]["org_id"]

    r = client.get(f"/dashboard?org_id={other_org_id}", headers=headers)

    assert r.status_code == 403


def test_employee_cannot_access_admin_dashboard(client):
    headers, data = login(client, "priya@northwind.test", "Northwind Logistics")
    org_id = next(o["org_id"] for o in data["organizations"] if o["org_name"] == "Northwind Logistics")

    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)

    assert r.status_code == 403
