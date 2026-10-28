import json
from pathlib import Path

import httpx
import pytest

from app import models
from app.db import SessionLocal
from app.services import llm
from app.services.scoring import (
    ATTEMPTS,
    DEFAULT_REASON,
    MAX_SCORE,
    MIN_SCORE,
    ScoringError,
    score_open_answer,
    validate_score,
)
from tests.conftest import login

MOCK_PATH = Path(__file__).resolve().parents[1] / "data" / "mock_ai_responses.json"

VALID = '{"score": 4, "reason": "Weekly drafting with a review step.", "flags": ["unreviewed_output"]}'

# Model output that must be rejected (score unusable or no JSON at all).
INVALID_OUTPUTS = {
    "score_above_range": '{"score": 7, "reason": "Excellent.", "flags": []}',
    "score_below_range": '{"score": 0, "reason": "None.", "flags": []}',
    "boolean_score": '{"score": true, "reason": "Yes.", "flags": []}',
    "non_numeric_score": '{"score": "four", "reason": "Good.", "flags": []}',
    "missing_score": '{"reason": "Regular use.", "flags": []}',
    "no_json_object": "the model wrote a sentence instead of JSON",
}


def _membership(db, email, org_name="Northwind Logistics"):
    return (
        db.query(models.Membership)
        .join(models.User)
        .join(models.Organization)
        .filter(models.User.email == email, models.Organization.name == org_name)
        .one()
    )


def _submit_open(client, headers, answer="I drafted replies with AI and edited them."):
    return client.post(
        "/diagnostic/submit",
        headers=headers,
        json={"answers": [{"question_id": "common-open", "answer": answer}]},
    )


# --- unit: accepted output -------------------------------------------------


def test_valid_output_is_accepted():
    assert validate_score('{"score": 4, "reason": "Check.", "flags": []}') == {
        "score": 4,
        "reason": "Check.",
        "flags": [],
    }


def test_fenced_json_is_accepted():
    raw = '```json\n{"score": 4, "reason": "Thoughtful use.", "flags": []}\n```'
    assert validate_score(raw)["score"] == 4


def test_surrounding_prose_is_accepted():
    raw = 'Sure, here is the JSON: {"score": 5, "reason": "Advanced.", "flags": []} Hope that helps.'
    assert validate_score(raw)["score"] == 5


def test_unknown_flags_are_dropped_and_allowed_kept_without_duplicates():
    raw = json.dumps({"score": 2, "reason": "Ok.",
                      "flags": ["probably_lying", "unreviewed_output", "unreviewed_output"]})
    assert validate_score(raw)["flags"] == ["unreviewed_output"]


def test_non_list_flags_become_empty():
    for value in ('"unreviewed_output"', "123", "null", '{"unreviewed_output": true}', "[1]"):
        raw = '{{"score": 3, "reason": "Ok.", "flags": {0}}}'.format(value)
        assert validate_score(raw)["flags"] == []


def test_missing_or_blank_reason_gets_default():
    assert validate_score('{"score": 3, "flags": []}')["reason"] == DEFAULT_REASON
    assert validate_score('{"score": 3, "reason": "   ", "flags": []}')["reason"] == DEFAULT_REASON


# --- unit: rejected output -------------------------------------------------


def test_score_below_range_is_rejected():
    for raw in ('{"score": 0, "reason": "None.", "flags": []}',
                '{"score": -3, "reason": "None.", "flags": []}'):
        with pytest.raises(ScoringError):
            validate_score(raw)


def test_score_above_range_is_rejected():
    for raw in ('{"score": 6, "reason": "Great.", "flags": []}',
                '{"score": 7, "reason": "Great.", "flags": []}'):
        with pytest.raises(ScoringError):
            validate_score(raw)


def test_boolean_score_is_rejected():
    with pytest.raises(ScoringError):
        validate_score('{"score": true, "reason": "Yes.", "flags": []}')


def test_non_numeric_score_is_rejected():
    with pytest.raises(ScoringError):
        validate_score('{"score": "four", "reason": "Good.", "flags": []}')


def test_fractional_score_is_rejected():
    with pytest.raises(ScoringError):
        validate_score('{"score": 3.5, "reason": "Good.", "flags": []}')


def test_missing_score_is_rejected():
    with pytest.raises(ScoringError):
        validate_score('{"reason": "Regular use.", "flags": []}')


def test_text_without_a_json_object_is_rejected():
    for raw in ("not json at all", "", "[1, 2, 3]"):
        with pytest.raises(ScoringError):
            validate_score(raw)


# --- model call: retry then controlled error -------------------------------


def test_model_failure_is_retried_once_then_raises(monkeypatch):
    calls = []

    def boom(question, answer):
        calls.append(1)
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(llm, "score_answer", boom)
    with pytest.raises(ScoringError):
        score_open_answer("Q", "A")
    assert len(calls) == ATTEMPTS


def test_retry_succeeds_on_second_attempt(monkeypatch):
    responses = iter(['{"score": 9, "reason": "Bad.", "flags": []}', VALID])
    monkeypatch.setattr(llm, "score_answer", lambda question, answer: next(responses))
    assert score_open_answer("Q", "A")["score"] == 4


# --- every mock fixture ----------------------------------------------------


@pytest.mark.parametrize("index", range(10))
def test_each_mock_fixture(index):
    canned = json.loads(MOCK_PATH.read_text())
    raw = canned[index]
    # Entries 5 (score 7) and 7 ("four") have unusable scores; the other eight
    # must be salvaged (fence stripped, flags dropped, missing reason defaulted).
    if index in {5, 7}:
        with pytest.raises(ScoringError):
            validate_score(raw)
        return
    result = validate_score(raw)
    assert MIN_SCORE <= result["score"] <= MAX_SCORE
    assert result["reason"].strip()
    assert set(result["flags"]) <= {"customer_data_shared", "confidential_data_shared",
                                    "unreviewed_output", "policy_unaware"}


# --- API: rejected output is never persisted --------------------------------


@pytest.mark.parametrize("raw", INVALID_OUTPUTS.values(), ids=list(INVALID_OUTPUTS))
def test_invalid_scoring_output_is_not_persisted(client, monkeypatch, raw):
    headers, _ = login(client, "neha@northwind.test", "Northwind Logistics")
    monkeypatch.setattr(llm, "score_answer", lambda question, answer, _raw=raw: _raw)

    response = _submit_open(client, headers)

    assert response.status_code == 502
    db = SessionLocal()
    try:
        member = _membership(db, "neha@northwind.test")
        assert db.query(models.Response).filter_by(
            membership_id=member.id, question_id="common-open"
        ).all() == []
    finally:
        db.close()


def test_model_timeout_is_controlled_and_not_persisted(client, monkeypatch):
    headers, _ = login(client, "neha@northwind.test", "Northwind Logistics")

    def boom(question, answer):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(llm, "score_answer", boom)

    assert _submit_open(client, headers).status_code == 502
    db = SessionLocal()
    try:
        member = _membership(db, "neha@northwind.test")
        assert db.query(models.Response).filter_by(
            membership_id=member.id, question_id="common-open"
        ).count() == 0
    finally:
        db.close()


def test_valid_output_is_persisted(client, monkeypatch):
    headers, _ = login(client, "neha@northwind.test", "Northwind Logistics")
    monkeypatch.setattr(llm, "score_answer", lambda question, answer: VALID)

    assert _submit_open(client, headers).status_code == 200
    db = SessionLocal()
    try:
        member = _membership(db, "neha@northwind.test")
        row = db.query(models.Response).filter_by(
            membership_id=member.id, question_id="common-open"
        ).one()
        assert row.score == 4
        assert row.reason == "Weekly drafting with a review step."
        assert row.flags == ["unreviewed_output"]
    finally:
        db.close()


def test_tolerant_output_is_saved_as_a_complete_answer(client, monkeypatch):
    headers, _ = login(client, "neha@northwind.test", "Northwind Logistics")
    fenced = '```json\n{"score": 3, "flags": ["unreviewed_output", "invented_flag"]}\n```'
    monkeypatch.setattr(llm, "score_answer", lambda question, answer: fenced)

    assert _submit_open(client, headers).status_code == 200
    db = SessionLocal()
    try:
        member = _membership(db, "neha@northwind.test")
        row = db.query(models.Response).filter_by(
            membership_id=member.id, question_id="common-open"
        ).one()
        assert row.score == 3
        assert row.reason == DEFAULT_REASON
        assert row.flags == ["unreviewed_output"]
    finally:
        db.close()
