from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth import verify_password, make_token, current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class SelectOrgIn(BaseModel):
    org_id: int


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    orgs = [
        {"org_id": m.org_id, "org_name": m.org.name, "role": m.role}
        for m in user.memberships
    ]
    return {"token": make_token(user.id), "name": user.name, "organizations": orgs}


@router.post("/select-org")
def select_org(
    body: SelectOrgIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # Only issue an org-scoped token if the user is really a member of that org.
    membership = (
        db.query(models.Membership)
        .filter_by(user_id=user.id, org_id=body.org_id)
        .first()
    )
    if membership is None:
        raise HTTPException(403, "Not a member of this organization")
    return {"token": make_token(user.id, body.org_id), "org_id": body.org_id}
