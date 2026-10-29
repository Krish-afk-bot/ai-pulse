"""Creates demo data. Run: python -m app.seed

All passwords are: pulse123
"""
from .db import Base, engine, SessionLocal
from . import models
from .auth import hash_password
from .services.assessment import ALLOWED_RISK_FLAGS
from .services.questions import questions_for

PEOPLE_NORTHWIND = [
    # name, email, department, role, job_role, seniority
    ("Asha Rao", "asha@northwind.test", None, "admin", "manager", "lead"),
    ("Vikram Shah", "vikram@northwind.test", "Sales", "employee", "sales", "senior"),
    ("Neha Gupta", "neha@northwind.test", "Sales", "employee", "sales", "junior"),
    ("Rohan Mehta", "rohan@northwind.test", "Sales", "employee", "sales", "mid"),
    ("Priya Nair", "priya@northwind.test", "Support", "employee", "support", "junior"),
    ("Arjun Iyer", "arjun@northwind.test", "Support", "employee", "support", "senior"),
    ("Kavitha Menon", "kavitha@northwind.test", "Support", "employee", "support", "mid"),
    ("Meghna Joshi", "meghna@northwind.test", "Support", "employee", "support", "junior"),
    ("Farhan Ali", "farhan@northwind.test", "Support", "employee", "support", "mid"),
    ("Dev Malhotra", "dev@northwind.test", "Engineering", "employee", "engineering", "lead"),
    ("Sara Thomas", "sara@northwind.test", "Engineering", "employee", "engineering", "mid"),
    ("Imran Khan", "imran@northwind.test", "HR", "employee", "manager", "senior"),
]
PEOPLE_BLUEPEAK = [
    ("Meera Pillai", "meera@bluepeak.test", None, "admin", "manager", "lead"),
    ("Tom Fernandes", "tom@bluepeak.test", "Stores", "employee", "sales", "mid"),
    ("Lina George", "lina@bluepeak.test", "Stores", "employee", "sales", "junior"),
    ("Kabir Das", "kabir@bluepeak.test", "Customer Care", "employee", "support", "senior"),
]


def add_complete_assessment(db, membership, tendency, flags=()):
    """Add one valid Response per question so completed_responses() accepts it.

    ``tendency`` is 2-4: MCQs pick the option closest to it and open answers use it
    as the score. It is deterministic, so each person gets a stable, different average.
    """
    risk_flags = [flag for flag in flags if flag in ALLOWED_RISK_FLAGS]
    for question in questions_for(membership.job_role, membership.seniority):
        is_open = question["type"] == "open"
        if is_open:
            answer, score = "Used AI on a real task and reviewed the output.", tendency
        else:
            option = min(question["options"], key=lambda item: abs(item["points"] - tendency))
            answer, score = option["text"], option["points"]
        db.add(models.Response(
            membership_id=membership.id,
            question_id=question["id"],
            answer=answer,
            score=score,
            reason="Checked the AI output before using it." if is_open else None,
            flags=risk_flags if is_open else [],
        ))


def run(with_demo=True):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    def make_org(name, depts):
        org = models.Organization(name=name)
        db.add(org)
        db.flush()
        d = {}
        for dn in depts:
            dept = models.Department(org_id=org.id, name=dn)
            db.add(dept)
            db.flush()
            d[dn] = dept.id
        return org, d

    nw, nw_depts = make_org("Northwind Logistics", ["Sales", "Support", "Engineering", "HR"])
    bp, bp_depts = make_org("Bluepeak Retail", ["Stores", "Customer Care"])

    users = {}

    def add_people(org, depts, people):
        for name, email, dept, role, job_role, seniority in people:
            u = users.get(email)
            if not u:
                u = models.User(name=name, email=email, password_hash=hash_password("pulse123"))
                db.add(u)
                db.flush()
                users[email] = u
            db.add(models.Membership(
                user_id=u.id, org_id=org.id,
                department_id=depts.get(dept) if dept else None,
                role=role, job_role=job_role, seniority=seniority,
            ))

    add_people(nw, nw_depts, PEOPLE_NORTHWIND)
    add_people(bp, bp_depts, PEOPLE_BLUEPEAK)

    # A consultant who works with both companies
    add_people(nw, nw_depts, [("Ravi Kapoor", "ravi@consult.test", "HR", "employee", "manager", "senior")])
    add_people(bp, bp_depts, [("Ravi Kapoor", "ravi@consult.test", None, "admin", "manager", "senior")])
    db.flush()

    # Some existing results so dashboards aren't empty
    def answer(email, org, qid, text, score, reason=None, flags=None):
        m = db.query(models.Membership).filter_by(user_id=users[email].id, org_id=org.id).first()
        db.add(models.Response(membership_id=m.id, question_id=qid, answer=text, score=score, reason=reason, flags=flags or []))

    answer("vikram@northwind.test", nw, "common-freq", "Daily", 4)
    answer("vikram@northwind.test", nw, "common-open", "Used ChatGPT to draft 20 follow-up emails and edited each one.", 4, "Regular use with editing.", [])
    answer("priya@northwind.test", nw, "common-freq", "A few times a month", 2)
    answer("priya@northwind.test", nw, "common-open", "Pasted a customer's complaint thread into ChatGPT to summarise it.", 3, "Useful summary but shared customer data.", ["customer_data_shared"])
    answer("kabir@bluepeak.test", bp, "common-open", "Uploaded our full customer refund list to an AI tool to find patterns.", 3, "Good idea, unsafe data handling.", ["customer_data_shared", "confidential_data_shared"])
    answer("kabir@bluepeak.test", bp, "common-freq", "Daily", 4)

    # Completed diagnostics, so the dashboard has real numbers. Priya and Vikram
    # keep their partial answers on purpose, so Priya can finish hers in a demo.
    def complete(email, org, tendency, flags=()):
        member = db.query(models.Membership).filter_by(user_id=users[email].id, org_id=org.id).first()
        add_complete_assessment(db, member, tendency, flags)

    if with_demo:
        complete("arjun@northwind.test", nw, 2, ["unreviewed_output"])
        complete("kavitha@northwind.test", nw, 4, ["unreviewed_output"])
        complete("meghna@northwind.test", nw, 3, ["unreviewed_output"])
        complete("farhan@northwind.test", nw, 2, ["unreviewed_output", "customer_data_shared"])
        complete("neha@northwind.test", nw, 4, ["customer_data_shared"])
        complete("rohan@northwind.test", nw, 3, ["customer_data_shared"])
        complete("dev@northwind.test", nw, 4, ["unreviewed_output"])
        complete("sara@northwind.test", nw, 2)
        complete("imran@northwind.test", nw, 3)
        complete("ravi@consult.test", nw, 4)
        complete("tom@bluepeak.test", bp, 3)
        complete("lina@bluepeak.test", bp, 2)

    db.commit()
    db.close()
    print("Seeded. Log in with any seeded email and password 'pulse123'.")


if __name__ == "__main__":
    run()
