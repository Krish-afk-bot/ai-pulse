from app.services.questions import questions_for


def ids(qs):
    return {q["id"] for q in qs}


def test_everyone_gets_common_questions():
    got = ids(questions_for("sales", "junior"))
    assert {"common-freq", "common-policy", "common-data", "common-review", "common-open"} <= got


def test_junior_engineer_does_not_get_senior_questions():
    got = ids(questions_for("engineering", "junior"))
    assert "eng-assistant" in got
    assert "eng-review" not in got
    assert "eng-arch" not in got


def test_mid_engineer_gets_mid_questions_but_not_senior_questions():
    got = ids(questions_for("engineering", "mid"))
    assert "eng-assistant" in got
    assert "eng-review" in got
    assert "eng-arch" not in got


def test_senior_engineer_gets_senior_questions():
    got = ids(questions_for("engineering", "senior"))
    assert "eng-arch" in got


def test_senior_support_gets_escalation_question():
    assert "sup-escalation" in ids(questions_for("support", "senior"))


def test_lead_manager_gets_policy_questions():
    got = ids(questions_for("manager", "lead"))
    assert "mgr-policy" in got
    assert "mgr-open" in got
