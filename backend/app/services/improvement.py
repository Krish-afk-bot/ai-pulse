"""Employee-facing evidence and improvement plan for one assessment.

Everything returned here is derived from the authenticated membership's own
saved responses plus the existing question bank. Saved assessment evidence
(answers, scores, stored rationales, risk flags) is reported as-is. Next steps
and their explanations are generated text derived from that evidence; nothing
is invented when the underlying data does not support it.

The plan deliberately reuses the existing building blocks:
- ``questions_for`` for the assigned question metadata,
- ``completed_responses`` for assessment validity (no duplicated scoring rules),
- ``maturity_level`` for the overall maturity label,
- ``NEXT_STEPS`` (moved here from the reports route) for role-level guidance.
"""

from ..utils import maturity_level
from .assessment import completed_responses
from .questions import questions_for

# Scores below this are treated as an improvement opportunity. This matches the
# scoring rubric used for open answers ("4 = regular, thoughtful use with
# review of outputs"), which is the first level at which review is expected.
GAP_THRESHOLD = 4.0
MIN_RECOMMENDATIONS = 2
MAX_RECOMMENDATIONS = 3

# Role-level next steps shown on the personal report. Kept here so the
# improvement plan reuses the same guidance instead of duplicating it.
NEXT_STEPS = {
    "support": [
        "Use AI to draft first replies, then edit",
        "Summarise long ticket threads before escalating",
        "Never paste customer details into public chatbots",
    ],
    "engineering": [
        "Use a code assistant for tests and refactors",
        "Review every AI suggestion before merging",
        "Keep secrets and customer data out of prompts",
    ],
    "sales": [
        "Draft outreach emails with AI and personalise them",
        "Summarise call notes into CRM updates",
        "Check AI-written claims before sending",
    ],
    "manager": [
        "Agree an AI usage policy with your team",
        "Pick one workflow per quarter to improve with AI",
        "Track time saved, not tool licences",
    ],
}

# Concrete follow-ups for the risk labels the scoring service can emit. These
# are generated action text; each is grounded in a real stored flag.
RISK_ACTIONS = {
    "customer_data_shared": "Strip or anonymise customer details before pasting text into an AI tool.",
    "confidential_data_shared": "Keep confidential company information out of AI prompts.",
    "unreviewed_output": "Review and edit AI output before relying on it at work.",
    "policy_unaware": "Read the company AI policy and confirm which tools are approved.",
}

NOTE = (
    "Answers, scores, stored rationales and risk flags are saved assessment "
    "evidence. Next steps and explanations are generated from that evidence."
)

_EMPTY_MESSAGE = (
    "No assessment answers are saved for this organization yet. Complete the "
    "diagnostic to see your evidence and next steps."
)
_INCOMPLETE_MESSAGE = (
    "Your saved answers do not form one complete, valid assessment yet. "
    "Resubmit every assigned question to see your evidence and next steps."
)
_MCQ_RATIONALE_NOTE = (
    "This question is scored from your multiple-choice selection; the "
    "assessment stores no written rationale for it."
)


def _base_plan(membership, expected, answered):
    return {
        "status": "empty",
        "message": "",
        "note": NOTE,
        "job_role": membership.job_role,
        "seniority": membership.seniority,
        "answered": answered,
        "expected": expected,
        "average_score": None,
        "level": maturity_level(None),
        "areas": [],
        "gaps": [],
        "recommendations": [],
    }


def _area(question, row):
    """Saved evidence for one assigned question, as stored."""
    is_open = question["type"] == "open"
    reason = row.reason if isinstance(row.reason, str) and row.reason.strip() else None
    if reason:
        rationale_note = None
    elif is_open:
        rationale_note = "The assessment stored no written rationale for this answer."
    else:
        rationale_note = _MCQ_RATIONALE_NOTE
    return {
        "question_id": question["id"],
        "question": question["text"],
        "type": question["type"],
        "scope": "core" if question["roles"] == ["all"] else "role_specific",
        "answer": row.answer,
        "score": row.score,
        "rationale": reason,
        "rationale_available": reason is not None,
        "rationale_note": rationale_note,
        "flags": list(row.flags or []),
    }


def _gaps(areas):
    gaps = []
    for area in sorted(areas, key=lambda item: item["score"]):
        if area["score"] >= GAP_THRESHOLD:
            continue
        gaps.append({
            "question_id": area["question_id"],
            "question": area["question"],
            "score": area["score"],
            "reason": "Your answer scored {}/5, below the {:.0f}/5 improvement threshold.".format(
                area["score"], GAP_THRESHOLD
            ),
            "flags": area["flags"],
        })
    return gaps


def _evidence(question, row, flags):
    return {
        "question_id": question["id"],
        "question": question["text"],
        "your_answer": row.answer,
        "your_score": row.score,
        "flags": flags,
    }


def _area_recommendation(question, row):
    """One evidence-linked action for a below-threshold question, or None."""
    flags = list(row.flags or [])
    if flags:
        action = RISK_ACTIONS.get(flags[0])
        if action:
            return {
                "action": action,
                "source": "risk_flag",
                "evidence": _evidence(question, row, flags),
                "explanation": (
                    "The saved answer for \u201c{0}\u201d was flagged \u201c{1}\u201d, "
                    "so this follow-up targets that risk.".format(question["text"], flags[0])
                ),
            }
    if question["type"] == "mcq":
        top = max(question["options"], key=lambda option: option["points"])
        if top["points"] > row.score:
            return {
                "action": "Work toward \u201c{0}\u201d for \u201c{1}\u201d.".format(
                    top["text"], question["text"]
                ),
                "source": "question_metadata",
                "evidence": _evidence(question, row, flags),
                "explanation": (
                    "Your saved answer \u201c{0}\u201d scored {1}/5, while this "
                    "question's top level is \u201c{2}\u201d.".format(
                        row.answer, row.score, top["text"]
                    )
                ),
            }
    return None


def _role_recommendation(membership, action):
    return {
        "action": action,
        "source": "role_guidance",
        "evidence": {
            "job_role": membership.job_role,
            "seniority": membership.seniority,
        },
        "explanation": (
            "Standard next step for the \u201c{0}\u201d role at \u201c{1}\u201d seniority; "
            "not tied to one specific saved answer.".format(
                membership.job_role, membership.seniority
            )
        ),
    }


def _recommendations(membership, pairs):
    recommendations = []
    # Risk flags take priority, then the lowest scores.
    ranked = sorted(pairs, key=lambda pair: (0 if pair[1].flags else 1, pair[1].score))
    for question, row in ranked:
        if len(recommendations) >= MAX_RECOMMENDATIONS:
            break
        if row.score >= GAP_THRESHOLD:
            continue
        recommendation = _area_recommendation(question, row)
        if recommendation:
            recommendations.append(recommendation)

    guidance = NEXT_STEPS.get(membership.job_role, NEXT_STEPS["manager"])
    for action in guidance:
        if len(recommendations) >= MIN_RECOMMENDATIONS:
            break
        recommendations.append(_role_recommendation(membership, action))

    return recommendations[:MAX_RECOMMENDATIONS]


def build_improvement_plan(membership, rows):
    """Build the explainable evidence and improvement plan for one membership."""
    questions = questions_for(membership.job_role, membership.seniority)
    plan = _base_plan(membership, len(questions), len(rows))

    if not rows:
        plan["message"] = _EMPTY_MESSAGE
        return plan

    ordered = completed_responses(membership, rows)
    if ordered is None:
        plan["status"] = "incomplete"
        plan["message"] = _INCOMPLETE_MESSAGE
        return plan

    pairs = list(zip(questions, ordered))
    areas = [_area(question, row) for question, row in pairs]
    average = sum(row.score for _, row in pairs) / len(pairs)

    plan.update({
        "status": "available",
        "message": "",
        "answered": len(ordered),
        "average_score": round(average, 2),
        "level": maturity_level(average),
        "areas": areas,
        "gaps": _gaps(areas),
        "recommendations": _recommendations(membership, pairs),
    })
    if not plan["gaps"]:
        plan["message"] = (
            "No assessment area scored below the {:.0f}/5 improvement "
            "threshold.".format(GAP_THRESHOLD)
        )
    return plan
