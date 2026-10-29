from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth import current_membership
from ..services.assessment import completed_responses
from ..utils import maturity_level

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# A department (or the pooled "Other teams" row) is only shown once at least this
# many distinct people have a complete assessment, so nobody can be identified.
MIN_GROUP_SIZE = 5


def _row(name, employees, completed, is_group):
    """One dashboard row. The average is the average of each person's average."""
    averages = [sum(row.score for row in rows) / len(rows) for _, rows in completed if rows]
    average = sum(averages) / len(averages) if averages else None
    return {
        "department": name,
        "employees": employees,
        "responded": len(completed),
        "average_score": round(average, 2) if average is not None else None,
        "level": maturity_level(average),
        "is_group": is_group,
    }


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
    pool = {}            # user_id -> (membership, rows), deduped across small groups
    pool_employees = 0   # members of the small departments that went into the pool

    def count_flags(completed):
        for member, rows in completed:
            flags = {flag for row in rows for flag in (row.flags or [])}
            for flag in flags:
                organization_flag_members.setdefault(flag, set()).add(member.user_id)

    for dept in org.departments:
        dept_members = [member for member in members if member.department_id == dept.id]
        completed_by_user = {}
        for member in dept_members:
            rows = db.query(models.Response).filter_by(membership_id=member.id).all()
            valid_rows = completed_responses(member, rows)
            if valid_rows is not None:
                completed_by_user.setdefault(member.user_id, (member, valid_rows))
        completed = list(completed_by_user.values())

        if len(completed) >= MIN_GROUP_SIZE:
            departments.append(_row(dept.name, len(dept_members), completed, False))
            count_flags(completed)
        elif completed:
            # Too small to be named: pool the people, never the department. A
            # department with no completed users adds nothing at all.
            pool_employees += len(dept_members)
            for user_id, entry in completed_by_user.items():
                pool.setdefault(user_id, entry)

    # The pool is shown only when it is itself big enough to stay anonymous.
    if len(pool) >= MIN_GROUP_SIZE:
        pooled = list(pool.values())
        departments.append(_row("Other teams", pool_employees, pooled, True))
        count_flags(pooled)

    # Only people in a released row may contribute to organization risks, and a
    # flag needs MIN_GROUP_SIZE distinct people to be reported.
    top_risks = [
        (flag, len(user_ids))
        for flag, user_ids in organization_flag_members.items()
        if len(user_ids) >= MIN_GROUP_SIZE
    ]
    return {
        "organization": org.name,
        "min_group_size": MIN_GROUP_SIZE,
        "departments": departments,
        "top_risks": sorted(top_risks, key=lambda item: -item[1])[:5],
    }
