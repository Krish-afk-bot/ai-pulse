from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth import current_membership
from ..services.assessment import completed_responses

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def level_for(avg):
    if avg is None:
        return "Not assessed"
    if avg < 1.5:
        return "Beginner"
    if avg < 2.5:
        return "Exploring"
    if avg < 3.5:
        return "Practitioner"
    return "Leader"


@router.get("")
def org_dashboard(org_id: int, m: models.Membership = Depends(current_membership), db: Session = Depends(get_db)):
    if m.role != "admin":
        raise HTTPException(403, "Admins only")
    if org_id != m.org_id:
        raise HTTPException(403, "Not authorized to access this organization")

    org = db.get(models.Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    members = db.query(models.Membership).filter_by(org_id=org_id).all()
    departments = []
    organization_flag_members = {}
    for dept in org.departments:
        dept_members = [member for member in members if member.department_id == dept.id]
        completed_by_user = {}
        for member in dept_members:
            rows = db.query(models.Response).filter_by(membership_id=member.id).all()
            valid_rows = completed_responses(member, rows)
            if valid_rows is not None:
                completed_by_user.setdefault(member.user_id, (member, valid_rows))
        completed = list(completed_by_user.values())

        # Do not return any department-level metadata or metrics for small groups.
        if len(completed) < 5:
            continue

        employee_averages = [
            sum(row.score for row in rows) / len(rows)
            for _, rows in completed
            if rows
        ]
        average = sum(employee_averages) / len(employee_averages) if employee_averages else None
        departments.append({
            "department": dept.name,
            "employees": len(dept_members),
            "responded": len(completed),
            "average_score": round(average, 2) if average is not None else None,
            "level": level_for(average),
        })

        for member, rows in completed:
            flags = {flag for row in rows for flag in (row.flags or [])}
            for flag in flags:
                organization_flag_members.setdefault(flag, set()).add(member.user_id)

    # Organization risk summaries use only eligible departments and require a
    # minimum of five distinct employees per flag to prevent small-group leakage.
    top_risks = [
        (flag, len(user_ids))
        for flag, user_ids in organization_flag_members.items()
        if len(user_ids) >= 5
    ]
    return {
        "organization": org.name,
        "departments": departments,
        "top_risks": sorted(top_risks, key=lambda item: -item[1])[:5],
    }
