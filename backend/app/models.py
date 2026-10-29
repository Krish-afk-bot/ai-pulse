from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Float, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    departments = relationship("Department", back_populates="org")


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(80))
    org = relationship("Organization", back_populates="departments")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    memberships = relationship("Membership", back_populates="user")


class Membership(Base):
    """A user's role inside one organization. Users can belong to several orgs."""
    __tablename__ = "memberships"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(20))        # "admin" | "employee"
    job_role: Mapped[str] = mapped_column(String(40))    # e.g. "support", "engineering", "sales", "manager"
    seniority: Mapped[str] = mapped_column(String(20))   # "junior" | "mid" | "senior" | "lead"
    user = relationship("User", back_populates="memberships")
    org = relationship("Organization")
    department = relationship("Department")


class Response(Base):
    __tablename__ = "responses"
    # One answer per membership and question. create_all() does not alter existing
    # tables, so an existing database needs a reseed to pick this constraint up.
    __table_args__ = (UniqueConstraint("membership_id", "question_id", name="uq_response_membership_question"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("memberships.id"))
    question_id: Mapped[str] = mapped_column(String(40))
    answer: Mapped[str] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
