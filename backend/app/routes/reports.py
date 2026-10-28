from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth import current_membership
from ..utils import maturity_level

router = APIRouter(prefix="/reports", tags=["reports"])

NEXT_STEPS = {
    "support": ["Use AI to draft first replies, then edit", "Summarise long ticket threads before escalating", "Never paste customer details into public chatbots"],
    "engineering": ["Use a code assistant for tests and refactors", "Review every AI suggestion before merging", "Keep secrets and customer data out of prompts"],
    "sales": ["Draft outreach emails with AI and personalise them", "Summarise call notes into CRM updates", "Check AI-written claims before sending"],
    "manager": ["Agree an AI usage policy with your team", "Pick one workflow per quarter to improve with AI", "Track time saved, not tool licences"],
}


@router.get("/me")
def my_report(m: models.Membership = Depends(current_membership), db: Session = Depends(get_db)):
    rows = db.query(models.Response).filter_by(membership_id=m.id).all()
    scores = [r.score for r in rows if r.score is not None]
    avg = sum(scores) / len(scores) if scores else None
    flags = sorted({f for r in rows for f in (r.flags or [])})
    return {
        "name": m.user.name,
        "organization": m.org.name,
        "answered": len(rows),
        "average_score": round(avg, 2) if avg is not None else None,
        "level": maturity_level(avg),
        "risks": flags,
        "next_steps": NEXT_STEPS.get(m.job_role, NEXT_STEPS["manager"]),
    }


@router.delete("/me")
def delete_my_responses(m: models.Membership = Depends(current_membership), db: Session = Depends(get_db)):
    """Delete this user's assessment responses from the selected organization only."""
    if m.role != "employee":
        raise HTTPException(403, "Employees only")
    try:
        deleted = (
            db.query(models.Response)
            .filter_by(membership_id=m.id)
            .delete(synchronize_session=False)
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Unable to delete assessment responses")
    return {"deleted": deleted}
