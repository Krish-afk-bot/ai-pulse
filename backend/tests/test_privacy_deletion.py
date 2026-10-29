from app import models
from app.db import SessionLocal
from app.services.questions import questions_for
from tests.conftest import login


def _membership(db, email, org_name="Northwind Logistics"):
    return (
        db.query(models.Membership)
        .join(models.User)
        .join(models.Organization)
        .filter(models.User.email == email, models.Organization.name == org_name)
        .one()
    )


def _sales_roster(db, count, start=0):
    """Create a distinct-user Sales roster without changing seeded memberships."""
    org = db.query(models.Organization).filter_by(name="Northwind Logistics").one()
    department = db.query(models.Department).filter_by(org_id=org.id, name="Sales").one()
    roster = []
    for index in range(start, start + count):
        email = f"privacy-sales-{index}@northwind.test"
        user = db.query(models.User).filter_by(email=email).one_or_none()
        if user is None:
            user = models.User(name=f"Privacy Sales {index}", email=email, password_hash="unused-test-hash")
            db.add(user)
            db.flush()
        member = models.Membership(user_id=user.id, org_id=org.id, department_id=department.id,
                                   role="employee", job_role="sales", seniority="junior")
        db.add(member)
        db.flush()
        roster.append(member)
    return roster


def _add_complete_assessment(db, membership, flags=(), high_score=False):
    for question in questions_for(membership.job_role, membership.seniority):
        if question["type"] == "mcq":
            option = question["options"][-1 if high_score else 0]
            answer, score = option["text"], option["points"]
        else:
            answer, score = "A verified test answer", 5 if high_score else 3
        db.add(models.Response(
            membership_id=membership.id,
            question_id=question["id"],
            answer=answer,
            score=score,
            reason="test rationale" if question["type"] == "open" else None,
            flags=list(flags) if question["type"] == "open" else [],
        ))
    db.flush()


def _department_result(client, admin_headers):
    db = SessionLocal()
    try:
        org_id = db.query(models.Organization).filter_by(name="Northwind Logistics").one().id
    finally:
        db.close()
    response = client.get(f"/dashboard?org_id={org_id}", headers=admin_headers)
    assert response.status_code == 200
    return response.json()


def test_zero_completed_employees_are_suppressed(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    assert _department_result(client, admin_headers)["departments"] == []


def test_one_completed_employee_is_suppressed(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        roster = _sales_roster(db, 1)
        _add_complete_assessment(db, roster[0], ["customer_data_shared"])
        db.commit()
    finally:
        db.close()
    data = _department_result(client, admin_headers)
    assert "Sales" not in {dept["department"] for dept in data["departments"]}
    assert data["top_risks"] == []


def test_four_completed_employees_are_suppressed(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        roster = _sales_roster(db, 4)
        for member in roster:
            _add_complete_assessment(db, member, ["customer_data_shared"])
        db.commit()
    finally:
        db.close()
    data = _department_result(client, admin_headers)
    assert "Sales" not in {dept["department"] for dept in data["departments"]}
    assert data["top_risks"] == []


def test_incomplete_answers_do_not_count_as_completed(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        roster = _sales_roster(db, 5)
        for member in roster[:3]:
            _add_complete_assessment(db, member, ["customer_data_shared"])
        incomplete = roster[3]
        first_question = questions_for(incomplete.job_role, incomplete.seniority)[0]
        # One single answer is not a complete assessment.
        db.add(models.Response(membership_id=incomplete.id, question_id=first_question["id"],
                               answer=first_question["options"][0]["text"], score=1,
                               flags=["customer_data_shared"]))
        _add_complete_assessment(db, roster[4], ["customer_data_shared"])
        support_member = _membership(db, "priya@northwind.test")
        db.query(models.Response).filter_by(membership_id=support_member.id).delete(synchronize_session=False)
        _add_complete_assessment(db, support_member, ["policy_unaware"])
        db.commit()
        # Three complete + one partial + one complete = four, not five.
    finally:
        db.close()
    data = _department_result(client, admin_headers)
    assert "Sales" not in {dept["department"] for dept in data["departments"]}
    assert data["top_risks"] == []


def test_incomplete_department_does_not_leak_risk_when_another_department_is_eligible(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        roster = _sales_roster(db, 5)
        for member in roster:
            _add_complete_assessment(db, member, ["customer_data_shared"])
        support = db.query(models.Department).filter_by(name="Support").one()
        for index in range(2):
            user = models.User(name=f"Private Support {index}", email=f"private-support-{index}@northwind.test", password_hash="unused")
            db.add(user)
            db.flush()
            member = models.Membership(user_id=user.id, org_id=support.org_id, department_id=support.id,
                                       role="employee", job_role="support", seniority="junior")
            db.add(member)
            db.flush()
            _add_complete_assessment(db, member, ["policy_unaware"])
        db.commit()
    finally:
        db.close()

    data = _department_result(client, admin_headers)
    assert {department["department"] for department in data["departments"]} == {"Sales"}
    assert data["top_risks"] == [["customer_data_shared", 5]]


def test_five_distinct_completed_employees_make_department_eligible(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        roster = _sales_roster(db, 5)
        for member in roster:
            _add_complete_assessment(db, member, ["customer_data_shared"])
        db.commit()
    finally:
        db.close()
    db = SessionLocal()
    try:
        support_member = _membership(db, "priya@northwind.test")
        db.query(models.Response).filter_by(membership_id=support_member.id).delete(synchronize_session=False)
        _add_complete_assessment(db, support_member, ["policy_unaware"])
        db.commit()
    finally:
        db.close()
    data = _department_result(client, admin_headers)
    sales = next(dept for dept in data["departments"] if dept["department"] == "Sales")
    assert sales["responded"] == 5
    assert sales["average_score"] is not None
    assert data["top_risks"] == [["customer_data_shared", 5]]
    # Suppressed Support risk must not leak into the organization total.
    assert "policy_unaware" not in {flag for flag, _ in data["top_risks"]}


def test_employee_deletes_only_selected_organizations_responses_and_can_repeat(client):
    employee_headers, _ = login(client, "ravi@consult.test", "Northwind Logistics")
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        northwind_member = _membership(db, "ravi@consult.test", "Northwind Logistics")
        bluepeak_member = _membership(db, "ravi@consult.test", "Bluepeak Retail")
        other_employee = _membership(db, "priya@northwind.test")
        _add_complete_assessment(db, northwind_member)
        _add_complete_assessment(db, bluepeak_member)
        db.query(models.Response).filter_by(membership_id=other_employee.id).delete(synchronize_session=False)
        _add_complete_assessment(db, other_employee)
        db.commit()
        assert client.get("/reports/me", headers=employee_headers).json()["answered"] > 0

        # Even if a caller supplies another user's id, the endpoint has no
        # user-targeting input and still deletes only the selected membership.
        first = client.delete(f"/reports/me?user_id={other_employee.user_id}", headers=employee_headers)
        second = client.delete("/reports/me", headers=employee_headers)
        report = client.get("/reports/me", headers=employee_headers)
        assert first.status_code == 200
        assert first.json()["deleted"] > 0
        assert second.status_code == 200
        assert second.json()["deleted"] == 0
        assert report.status_code == 200
        assert report.json()["answered"] == 0
        assert db.query(models.Response).filter_by(membership_id=northwind_member.id).count() == 0
        assert db.query(models.Response).filter_by(membership_id=bluepeak_member.id).count() == len(
            questions_for(bluepeak_member.job_role, bluepeak_member.seniority)
        )
        assert db.query(models.Response).filter_by(membership_id=other_employee.id).count() == len(
            questions_for(other_employee.job_role, other_employee.seniority)
        )
    finally:
        db.close()


def test_employee_deletion_removes_completed_dashboard_contribution(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    employee_headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        support = db.query(models.Department).filter_by(name="Support").one()
        priya = _membership(db, "priya@northwind.test")
        db.query(models.Response).filter_by(membership_id=priya.id).delete(synchronize_session=False)
        _add_complete_assessment(db, priya, ["customer_data_shared"])
        for index in range(4):
            user = models.User(name=f"Support Test {index}", email=f"support-test-{index}@northwind.test", password_hash="unused")
            db.add(user)
            db.flush()
            member = models.Membership(user_id=user.id, org_id=support.org_id, department_id=support.id,
                                       role="employee", job_role="support", seniority="junior")
            db.add(member)
            db.flush()
            _add_complete_assessment(db, member, ["customer_data_shared"])
        db.commit()
    finally:
        db.close()

    before = _department_result(client, admin_headers)
    assert "Support" in {dept["department"] for dept in before["departments"]}
    assert client.delete("/reports/me", headers=employee_headers).status_code == 200
    after = _department_result(client, admin_headers)
    assert "Support" not in {dept["department"] for dept in after["departments"]}
    assert after["top_risks"] == []


def test_deleted_high_scoring_employee_no_longer_affects_visible_aggregate(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    employee_headers, _ = login(client, "vikram@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        vikram = _membership(db, "vikram@northwind.test")
        db.query(models.Response).filter_by(membership_id=vikram.id).delete(synchronize_session=False)
        _add_complete_assessment(db, vikram, ["customer_data_shared"], high_score=True)
        roster = _sales_roster(db, 5)
        for member in roster:
            _add_complete_assessment(db, member, ["customer_data_shared"])
        db.commit()
    finally:
        db.close()

    before = _department_result(client, admin_headers)
    before_sales = next(dept for dept in before["departments"] if dept["department"] == "Sales")
    assert before_sales["responded"] == 6
    assert before_sales["average_score"] > 1.5
    assert before["top_risks"] == [["customer_data_shared", 6]]

    assert client.delete("/reports/me", headers=employee_headers).status_code == 200
    after = _department_result(client, admin_headers)
    after_sales = next(dept for dept in after["departments"] if dept["department"] == "Sales")
    assert after_sales["responded"] == 5
    assert after_sales["average_score"] == 1.33
    assert after["top_risks"] == [["customer_data_shared", 5]]


def test_submission_rejects_duplicate_questions_and_updates_existing_response(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    question = next(question for question in questions_for("support", "junior") if question["type"] == "mcq")
    answer = question["options"][0]["text"]

    duplicate_payload = {"answers": [
        {"question_id": question["id"], "answer": answer},
        {"question_id": question["id"], "answer": answer},
    ]}
    assert client.post("/diagnostic/submit", headers=headers, json=duplicate_payload).status_code == 400

    first = client.post("/diagnostic/submit", headers=headers,
                        json={"answers": [{"question_id": question["id"], "answer": answer}]})
    second_answer = question["options"][1]["text"]
    second = client.post("/diagnostic/submit", headers=headers,
                         json={"answers": [{"question_id": question["id"], "answer": second_answer}]})
    assert first.status_code == 200
    assert second.status_code == 200

    db = SessionLocal()
    try:
        member = _membership(db, "priya@northwind.test")
        rows = db.query(models.Response).filter_by(membership_id=member.id, question_id=question["id"]).all()
        assert len(rows) == 1
        assert rows[0].answer == second_answer
    finally:
        db.close()


def test_admin_cannot_delete_assessment_data(client):
    admin_headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    assert client.delete("/reports/me", headers=admin_headers).status_code == 403


def test_dashboard_cross_tenant_access_still_denied(client):
    headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    _, bluepeak = login(client, "meera@bluepeak.test", "Bluepeak Retail")
    other_org_id = bluepeak["organizations"][0]["org_id"]
    assert client.get(f"/dashboard?org_id={other_org_id}", headers=headers).status_code == 403
