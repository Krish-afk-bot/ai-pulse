import json

from app import models
from app.db import SessionLocal
from tests.conftest import login
from tests.test_privacy_deletion import (
    _add_complete_assessment,
    _department_result,
    _membership,
    _sales_roster,
)


def _roster(db, department_name, count):
    """Create distinct completed-ready members in a named Northwind department."""
    org = db.query(models.Organization).filter_by(name="Northwind Logistics").one()
    department = db.query(models.Department).filter_by(org_id=org.id, name=department_name).one()
    roster = []
    for index in range(count):
        email = f"pool-{department_name.lower().replace(' ', '-')}-{index}@northwind.test"
        user = db.query(models.User).filter_by(email=email).one_or_none()
        if user is None:
            user = models.User(name=f"Pool {department_name} {index}", email=email, password_hash="unused-test-hash")
            db.add(user)
            db.flush()
        member = models.Membership(user_id=user.id, org_id=org.id, department_id=department.id,
                                   role="employee", job_role="sales", seniority="junior")
        db.add(member)
        db.flush()
        roster.append(member)
    return roster


def _small_departments(db, sizes, flags):
    """Complete assessments for several small departments; return every pooled member."""
    pooled = []
    for name, count in sizes.items():
        for member in _roster(db, name, count):
            _add_complete_assessment(db, member, flags)
            pooled.append(member)
    return pooled


def _names(data):
    return {row["department"] for row in data["departments"]}


def test_small_departments_pool_into_one_other_teams_row(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        _small_departments(db, {"Support": 2, "Engineering": 2, "HR": 2}, ["customer_data_shared"])
        db.commit()
    finally:
        db.close()

    data = _department_result(client, admin_headers)
    assert len(data["departments"]) == 1
    other = data["departments"][0]
    assert other["department"] == "Other teams"
    assert other["is_group"] is True
    assert other["responded"] == 6
    # None of the pooled department names may appear anywhere in the response.
    body = json.dumps(data)
    for name in ("Support", "Engineering", "HR"):
        assert name not in body


def test_pool_below_threshold_stays_completely_hidden(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        _small_departments(db, {"Support": 2, "Engineering": 2}, ["customer_data_shared"])
        db.commit()
    finally:
        db.close()

    data = _department_result(client, admin_headers)
    assert data["departments"] == []
    assert data["top_risks"] == []
    body = json.dumps(data)
    for name in ("Support", "Engineering"):
        assert name not in body


def test_eligible_department_and_pool_both_appear(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        for member in _sales_roster(db, 5):
            _add_complete_assessment(db, member, ["customer_data_shared"])
        _small_departments(db, {"Support": 2, "Engineering": 3}, ["policy_unaware"])
        db.commit()
    finally:
        db.close()

    data = _department_result(client, admin_headers)
    assert _names(data) == {"Sales", "Other teams"}
    sales = next(row for row in data["departments"] if row["department"] == "Sales")
    other = next(row for row in data["departments"] if row["department"] == "Other teams")
    assert sales["responded"] == 5
    assert sales["is_group"] is False
    assert other["responded"] == 5


def test_eligible_department_with_tiny_pool_shows_only_the_department(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        for member in _sales_roster(db, 5):
            _add_complete_assessment(db, member, ["customer_data_shared"])
        _small_departments(db, {"Support": 2, "Engineering": 2}, ["policy_unaware"])
        db.commit()
    finally:
        db.close()

    data = _department_result(client, admin_headers)
    assert _names(data) == {"Sales"}


def test_pooled_risk_flag_needs_five_distinct_users(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        members = []
        for name, count in {"Support": 3, "Engineering": 3}.items():
            members.extend(_roster(db, name, count))
        # Four users share customer_data_shared, five share policy_unaware.
        for index, member in enumerate(members):
            flags = []
            if index < 4:
                flags.append("customer_data_shared")
            if index < 5:
                flags.append("policy_unaware")
            _add_complete_assessment(db, member, flags)
        db.commit()
    finally:
        db.close()

    data = _department_result(client, admin_headers)
    assert data["top_risks"] == [["policy_unaware", 5]]


def test_employee_deletion_can_shrink_the_pool_below_threshold(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    employee_headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        priya = _membership(db, "priya@northwind.test")
        db.query(models.Response).filter_by(membership_id=priya.id).delete(synchronize_session=False)
        _add_complete_assessment(db, priya, ["customer_data_shared"])
        _small_departments(db, {"Support": 2, "Engineering": 2}, ["customer_data_shared"])
        db.commit()
    finally:
        db.close()

    before = _department_result(client, admin_headers)
    assert "Other teams" in _names(before)

    assert client.delete("/reports/me", headers=employee_headers).status_code == 200

    after = _department_result(client, admin_headers)
    assert "Other teams" not in _names(after)
    assert after["departments"] == []
