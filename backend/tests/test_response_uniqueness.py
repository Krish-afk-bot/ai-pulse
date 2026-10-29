from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.db import SessionLocal, engine, get_db
from app.main import app
from app.services.assessment import completed_responses
from app.services.questions import questions_for
from tests.conftest import login
from tests.test_privacy_deletion import _membership


def _mcq_payload(membership):
    """A valid submission of every multiple-choice question (no model calls)."""
    return {"answers": [
        {"question_id": question["id"], "answer": question["options"][0]["text"]}
        for question in questions_for(membership.job_role, membership.seniority)
        if question["type"] == "mcq"
    ]}


def test_duplicate_response_insert_raises_integrity_error(client):
    db = SessionLocal()
    try:
        member = _membership(db, "priya@northwind.test")
        db.query(models.Response).filter_by(membership_id=member.id).delete(synchronize_session=False)
        question = questions_for(member.job_role, member.seniority)[0]
        db.add(models.Response(membership_id=member.id, question_id=question["id"], answer="A", score=1))
        db.flush()
        db.add(models.Response(membership_id=member.id, question_id=question["id"], answer="B", score=1))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_completed_responses_rejects_duplicate_rows_in_memory():
    member = SimpleNamespace(job_role="support", seniority="junior")
    rows = []
    for question in questions_for("support", "junior"):
        if question["type"] == "mcq":
            rows.append(SimpleNamespace(question_id=question["id"], answer=question["options"][0]["text"],
                                        score=question["options"][0]["points"], reason=None, flags=[]))
        else:
            rows.append(SimpleNamespace(question_id=question["id"], answer="A real answer", score=3,
                                        reason="A stored rationale.", flags=[]))

    assert completed_responses(member, rows) is not None
    rows.append(SimpleNamespace(question_id=rows[0].question_id, answer=rows[0].answer,
                                score=rows[0].score, reason=None, flags=[]))
    assert completed_responses(member, rows) is None


class _RaceSession(Session):
    """A session whose Response reads miss the saved rows, emulating a double-click
    race where the second request checks for duplicates before the first one commits.
    Everything else (loading the membership) works normally."""

    def query(self, *entities, **kwargs):
        if models.Response in entities:
            class _Empty:
                def filter(self, *args, **kwargs):
                    return self

                def filter_by(self, *args, **kwargs):
                    return self

                def all(self):
                    return []
            return _Empty()
        return super().query(*entities, **kwargs)


def test_double_submit_returns_conflict_and_keeps_one_row_per_question(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    db = SessionLocal()
    try:
        membership = _membership(db, "priya@northwind.test")
        db.query(models.Response).filter_by(membership_id=membership.id).delete(synchronize_session=False)
        db.commit()
        payload = _mcq_payload(membership)
        question_ids = [answer["question_id"] for answer in payload["answers"]]
    finally:
        db.close()

    assert client.post("/diagnostic/submit", headers=headers, json=payload).status_code == 200

    race_db = _RaceSession(bind=engine)
    app.dependency_overrides[get_db] = lambda: race_db
    try:
        second = client.post("/diagnostic/submit", headers=headers, json=payload)
    finally:
        app.dependency_overrides.clear()
        race_db.close()

    assert second.status_code == 409
    assert second.json()["detail"] == "These answers were already saved. Refresh and try again."

    db = SessionLocal()
    try:
        membership = _membership(db, "priya@northwind.test")
        for question_id in question_ids:
            count = db.query(models.Response).filter_by(
                membership_id=membership.id, question_id=question_id).count()
            assert count == 1
        assert db.query(models.Response).filter_by(membership_id=membership.id).count() == len(question_ids)
    finally:
        db.close()
