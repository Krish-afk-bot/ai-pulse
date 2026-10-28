from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth import current_membership
from ..services.questions import questions_for, load_questions
from ..services.scoring import ScoringError, score_open_answer

router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=40)
    answer: str = Field(min_length=1, max_length=5000)


class SubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[AnswerIn] = Field(min_length=1)


@router.get("/questions")
def get_questions(m: models.Membership = Depends(current_membership)):
    qs = questions_for(m.job_role, m.seniority)
    # don't leak scoring points to the client
    return [
        {k: v for k, v in q.items() if k != "points"} | (
            {"options": [o["text"] for o in q["options"]]} if q["type"] == "mcq" else {}
        )
        for q in qs
    ]


@router.post("/submit")
def submit(body: SubmitIn, m: models.Membership = Depends(current_membership), db: Session = Depends(get_db)):
    assigned = {q["id"]: q for q in questions_for(m.job_role, m.seniority)}
    bank = {q["id"]: q for q in load_questions()}
    question_ids = [answer.question_id for answer in body.answers]
    if len(question_ids) != len(set(question_ids)):
        raise HTTPException(400, "Duplicate question responses are not allowed")
    existing_rows = (
        db.query(models.Response)
        .filter(models.Response.membership_id == m.id, models.Response.question_id.in_(question_ids))
        .all()
    )
    existing_by_question = {}
    for row in existing_rows:
        existing_by_question.setdefault(row.question_id, []).append(row)
    if any(len(rows) > 1 for rows in existing_by_question.values()):
        raise HTTPException(409, "Existing duplicate responses must be deleted before resubmitting")

    responses = []
    for answer in body.answers:
        question = assigned.get(answer.question_id)
        if question is None:
            raise HTTPException(400, f"Question {answer.question_id} is not assigned to this assessment")
        source = bank[question["id"]]
        cleaned_answer = answer.answer.strip()
        if not cleaned_answer:
            raise HTTPException(400, "Answers cannot be blank")
        response_rows = existing_by_question.get(question["id"], [])
        response = response_rows[0] if response_rows else models.Response(
            membership_id=m.id, question_id=question["id"]
        )
        response.answer = cleaned_answer
        response.score = None
        response.reason = None
        response.flags = None
        if source["type"] == "mcq":
            option = next((item for item in source["options"] if item["text"] == cleaned_answer), None)
            if option is None:
                raise HTTPException(400, f"Invalid option for {question['id']}")
            response.score = option["points"]
        else:
            try:
                result = score_open_answer(source["text"], cleaned_answer)
            except ScoringError:
                # Never persist (or fabricate) a score the model did not validly return.
                db.rollback()
                raise HTTPException(502, "Scoring service returned an invalid response")
            response.score = result["score"]
            response.reason = result["reason"]
            response.flags = result["flags"]
        responses.append(response)

    try:
        db.add_all(responses)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Unable to save assessment responses")
    return {"saved": len(responses)}
