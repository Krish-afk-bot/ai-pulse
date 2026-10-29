from app import models
from app.db import SessionLocal
from app.services.questions import questions_for
from tests.conftest import login


def _membership(email, org_name="Northwind Logistics"):
    db = SessionLocal()
    try:
        return (
            db.query(models.Membership)
            .join(models.User)
            .join(models.Organization)
            .filter(models.User.email == email, models.Organization.name == org_name)
            .one()
        )
    finally:
        db.close()


def _clear_responses(db, membership):
    db.query(models.Response).filter_by(membership_id=membership.id).delete(synchronize_session=False)


def _add_assessment(db, membership, low=True, flags=(), open_answer="Used AI to summarise a task and checked the result."):
    """Insert exactly one valid response per assigned question."""
    for question in questions_for(membership.job_role, membership.seniority):
        if question["type"] == "mcq":
            option = question["options"][0 if low else -1]
            answer, value = option["text"], option["points"]
        else:
            answer, value = open_answer, 2 if low else 5
        db.add(models.Response(
            membership_id=membership.id,
            question_id=question["id"],
            answer=answer,
            score=value,
            reason="Stored rationale for the open answer." if question["type"] == "open" else None,
            flags=list(flags) if question["type"] == "open" else [],
        ))
    db.flush()


def _plan(client, headers):
    response = client.get("/reports/me/improvement", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_valid_assessment_returns_evidence_backed_recommendations(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        member = _membership("priya@northwind.test")
        _clear_responses(db, member)
        _add_assessment(db, member, low=True)
        db.commit()
        assigned = {question["id"] for question in questions_for(member.job_role, member.seniority)}
    finally:
        db.close()

    plan = _plan(client, headers)

    assert plan["status"] == "available"
    assert len(plan["areas"]) == len(assigned)
    assert 2 <= len(plan["recommendations"]) <= 3
    for recommendation in plan["recommendations"]:
        assert recommendation["action"]
        assert recommendation["explanation"]
        assert recommendation["source"] in {"question_metadata", "risk_flag", "role_guidance"}

    evidence_linked = [r for r in plan["recommendations"] if r["source"] != "role_guidance"]
    assert evidence_linked, "low scores should produce evidence-linked recommendations"
    for recommendation in evidence_linked:
        assert recommendation["evidence"]["question_id"] in assigned


def test_recommendations_reference_real_questions(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        member = _membership("priya@northwind.test")
        _clear_responses(db, member)
        _add_assessment(db, member, low=True)
        db.commit()
        questions = {question["id"]: question for question in questions_for(member.job_role, member.seniority)}
    finally:
        db.close()

    plan = _plan(client, headers)

    for recommendation in plan["recommendations"]:
        if recommendation["source"] == "role_guidance":
            continue
        question_id = recommendation["evidence"]["question_id"]
        assert question_id in questions
        assert recommendation["evidence"]["question"] == questions[question_id]["text"]
        assert recommendation["evidence"]["your_answer"]


def test_risk_flag_produces_supported_recommendation(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        member = _membership("priya@northwind.test")
        _clear_responses(db, member)
        _add_assessment(db, member, low=True, flags=["customer_data_shared"])
        db.commit()
    finally:
        db.close()

    plan = _plan(client, headers)

    flagged = [r for r in plan["recommendations"] if r["source"] == "risk_flag"]
    assert flagged
    assert "customer_data_shared" in flagged[0]["evidence"]["flags"]
    assert any(gap["flags"] == ["customer_data_shared"] for gap in plan["gaps"])


def test_missing_rationale_never_produces_fabricated_evidence(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        member = _membership("priya@northwind.test")
        _clear_responses(db, member)
        _add_assessment(db, member, low=True)
        db.commit()
        open_ids = {
            question["id"]
            for question in questions_for(member.job_role, member.seniority)
            if question["type"] == "open"
        }
    finally:
        db.close()

    plan = _plan(client, headers)

    for area in plan["areas"]:
        if area["question_id"] in open_ids:
            assert area["rationale_available"] is True
            assert area["rationale"]
        else:
            # Multiple-choice areas store no written rationale; the plan reports
            # that explicitly instead of inventing one.
            assert area["rationale"] is None
            assert area["rationale_available"] is False
            assert area["rationale_note"]


def test_empty_assessment_returns_empty_state(client):
    headers, _ = login(client, "ravi@consult.test", "Northwind Logistics")
    plan = _plan(client, headers)

    assert plan["status"] == "empty"
    assert plan["areas"] == []
    assert plan["gaps"] == []
    assert plan["recommendations"] == []
    assert plan["average_score"] is None
    assert plan["message"]


def test_incomplete_assessment_returns_incomplete_state_without_recommendations(client):
    # The seed leaves Priya with only a partial set of answers.
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    plan = _plan(client, headers)

    assert plan["status"] == "incomplete"
    assert plan["areas"] == []
    assert plan["recommendations"] == []
    assert plan["message"]


def test_deleted_assessment_returns_empty_state(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        member = _membership("priya@northwind.test")
        _clear_responses(db, member)
        _add_assessment(db, member, low=True)
        db.commit()
    finally:
        db.close()

    assert _plan(client, headers)["status"] == "available"
    assert client.delete("/reports/me", headers=headers).status_code == 200

    plan = _plan(client, headers)
    assert plan["status"] == "empty"
    assert plan["areas"] == []
    assert plan["recommendations"] == []


def test_one_employee_cannot_retrieve_another_employees_plan(client):
    priya_headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    vikram_headers, _ = login(client, "vikram@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        priya = _membership("priya@northwind.test")
        vikram = _membership("vikram@northwind.test")
        _clear_responses(db, priya)
        _clear_responses(db, vikram)
        _add_assessment(db, priya, low=True, open_answer="Priya's private AI story.")
        _add_assessment(db, vikram, low=False, open_answer="Vikram's private AI story.")
        db.commit()
        priya_id = priya.id
    finally:
        db.close()

    priya_plan = _plan(client, priya_headers)
    vikram_plan = _plan(client, vikram_headers)
    assert priya_plan["status"] == "available"
    assert vikram_plan["status"] == "available"

    priya_answers = {area["answer"] for area in priya_plan["areas"]}
    vikram_answers = {area["answer"] for area in vikram_plan["areas"]}
    assert priya_answers.isdisjoint(vikram_answers)

    # There is no user/membership input; supplying one must not change the scope.
    response = client.get(f"/reports/me/improvement?user_id={priya_id}", headers=vikram_headers)
    assert response.status_code == 200
    assert {area["answer"] for area in response.json()["areas"]} == vikram_answers


def _add_custom_assessment(db, membership, mcq_answers, open_score=5):
    """Valid assessment: given MCQ answers, every other MCQ at its top option."""
    for question in questions_for(membership.job_role, membership.seniority):
        if question["type"] == "open":
            answer, score = "Used AI and reviewed the output.", open_score
        else:
            text = mcq_answers.get(question["id"], question["options"][-1]["text"])
            option = next(item for item in question["options"] if item["text"] == text)
            answer, score = option["text"], option["points"]
        db.add(models.Response(
            membership_id=membership.id,
            question_id=question["id"],
            answer=answer,
            score=score,
            reason="Stored rationale." if question["type"] == "open" else None,
            flags=[],
        ))


def _custom_plan(client, mcq_answers):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        member = _membership("priya@northwind.test")
        _clear_responses(db, member)
        _add_custom_assessment(db, member, mcq_answers)
        db.commit()
    finally:
        db.close()
    return _plan(client, headers)


def _by_question(plan, question_id):
    return next(r for r in plan["recommendations"] if r["evidence"].get("question_id") == question_id)


def test_mcq_gap_recommends_the_next_level_not_the_top_option(client):
    plan = _custom_plan(client, {"common-freq": "A few times a month"})

    frequency = _by_question(plan, "common-freq")
    assert "A few times a week" in frequency["action"]
    assert "Many times a day" not in frequency["action"]


def test_low_review_gap_ranks_above_low_frequency_gap(client):
    plan = _custom_plan(client, {"common-review": "Use it as is", "common-freq": "Never"})

    ids = [r["evidence"].get("question_id") for r in plan["recommendations"]]
    assert ids.index("common-review") < ids.index("common-freq")


def test_policy_gap_asks_the_person_to_read_the_policy(client):
    plan = _custom_plan(client, {"common-policy": "I think so, but I haven't read it"})

    policy = _by_question(plan, "common-policy")
    assert "AI policy" in policy["action"]
    assert "manager" in policy["action"]
    # At this level the answer is to read the policy, not to name the top option.
    assert "Yes, and I help others follow it" not in policy["action"]

