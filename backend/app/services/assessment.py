import math

from .questions import questions_for

ALLOWED_RISK_FLAGS = {
    "customer_data_shared",
    "confidential_data_shared",
    "unreviewed_output",
    "policy_unaware",
}


def completed_responses(membership, rows):
    """Return rows for one valid, complete assessment, or None if incomplete/invalid."""
    questions = questions_for(membership.job_role, membership.seniority)
    expected = {question["id"]: question for question in questions}
    if not expected or len(rows) != len(expected):
        return None

    by_question = {}
    for row in rows:
        if row.question_id not in expected or row.question_id in by_question:
            return None
        by_question[row.question_id] = row

    for question_id, question in expected.items():
        row = by_question.get(question_id)
        if row is None or not isinstance(row.answer, str) or not row.answer.strip():
            return None
        if isinstance(row.score, bool) or not isinstance(row.score, (int, float)):
            return None
        if not math.isfinite(row.score) or not 1 <= row.score <= 5:
            return None

        if question["type"] == "mcq":
            option = next((item for item in question["options"] if item["text"] == row.answer), None)
            if option is None or row.score != option["points"]:
                return None
        elif question["type"] != "open":
            return None

        flags = row.flags
        if question["type"] == "open" and (
            not isinstance(row.reason, str) or not row.reason.strip() or not isinstance(flags, list)
        ):
            return None
        if flags is not None and (
            not isinstance(flags, list)
            or any(not isinstance(flag, str) or flag not in ALLOWED_RISK_FLAGS for flag in flags)
        ):
            return None

    return [by_question[question["id"]] for question in questions]
