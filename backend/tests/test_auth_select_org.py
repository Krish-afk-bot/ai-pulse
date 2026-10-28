from tests.conftest import login


def test_select_org_rejects_an_org_you_are_not_in(client):
    headers, data = login(client, "asha@northwind.test")
    northwind_id = next(o["org_id"] for o in data["organizations"] if o["org_name"] == "Northwind Logistics")

    _, bluepeak = login(client, "meera@bluepeak.test")
    bluepeak_id = next(o["org_id"] for o in bluepeak["organizations"] if o["org_name"] == "Bluepeak Retail")

    assert client.post("/auth/select-org", json={"org_id": northwind_id}, headers=headers).status_code == 200
    assert client.post("/auth/select-org", json={"org_id": bluepeak_id}, headers=headers).status_code == 403


def test_consultant_can_select_either_org_they_belong_to(client):
    headers, data = login(client, "ravi@consult.test")
    assert len(data["organizations"]) == 2
    for org in data["organizations"]:
        assert client.post("/auth/select-org", json={"org_id": org["org_id"]}, headers=headers).status_code == 200
