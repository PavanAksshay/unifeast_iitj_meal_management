from __future__ import annotations

import hashlib
import hmac
import csv
import io
import os
import secrets
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint, create_engine, func, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

TZ = ZoneInfo("Asia/Kolkata")
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "local-only-change-me").encode()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./iitj_meals.sqlite3")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
app = FastAPI(title="UniFeast IITJ Meal Management API", version="1.0.0", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3100")], allow_methods=["*"], allow_headers=["*"])


class Base(DeclarativeBase):
    pass


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(160), unique=True)
    timezone: Mapped[str] = mapped_column(String(48), default="Asia/Kolkata")


class MessUnit(Base):
    __tablename__ = "mess_units"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"))
    name: Mapped[str] = mapped_column(String(160))
    capacity: Mapped[int] = mapped_column(Integer, default=0)


class Student(Base):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"))
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    roll_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    password_initialized: Mapped[bool] = mapped_column(default=False)
    photo_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(24), nullable=True)
    hostel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bed_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    course: Mapped[str | None] = mapped_column(String(120), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(120), nullable=True)


class StaffUser(Base):
    __tablename__ = "staff_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(30), index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OTPChallenge(Base):
    __tablename__ = "student_otp_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Allocation(Base):
    __tablename__ = "student_allocations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    source_batch_id: Mapped[str] = mapped_column(String(36))


class MealSchedule(Base):
    __tablename__ = "meal_schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"), index=True)
    meal_type: Mapped[str] = mapped_column(String(20))
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    __table_args__ = (UniqueConstraint("unit_id", "meal_type", name="uq_schedule_unit_meal"),)


class MealServiceOverride(Base):
    __tablename__ = "meal_service_overrides"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"), index=True)
    service_date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(20))
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    is_cancelled: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("unit_id", "service_date", "meal_type", name="uq_service_override_unit_date_meal"),)


class MealScheduleRevision(Base):
    __tablename__ = "meal_schedule_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"), index=True)
    meal_type: Mapped[str] = mapped_column(String(20))
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    __table_args__ = (UniqueConstraint("unit_id", "meal_type", "effective_from", name="uq_schedule_revision_unit_meal_date"),)


class MealPlan(Base):
    __tablename__ = "meal_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"), index=True)
    service_date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(20))
    menu: Mapped[list] = mapped_column(JSON, default=list)
    meal_category: Mapped[str] = mapped_column(String(20), default="Veg")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(TZ))
    __table_args__ = (UniqueConstraint("unit_id", "service_date", "meal_type", name="uq_plan_unit_date_meal"),)


class MealToken(Base):
    __tablename__ = "meal_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    reference: Mapped[str | None] = mapped_column(String(32), nullable=True)
    student_name_snapshot: Mapped[str | None] = mapped_column(String(160), nullable=True)
    roll_number_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit_name_snapshot: Mapped[str | None] = mapped_column(String(160), nullable=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"))
    meal_type: Mapped[str] = mapped_column(String(20))
    service_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MealServing(Base):
    __tablename__ = "meal_servings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"))
    meal_type: Mapped[str] = mapped_column(String(20))
    service_date: Mapped[date] = mapped_column(Date)
    served_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    collection_source: Mapped[str] = mapped_column(String(80), default="student-slide")
    token_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    __table_args__ = (UniqueConstraint("student_id", "unit_id", "meal_type", "service_date", name="uq_serving_student_unit_meal_day"),)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="preview")
    source_name: Mapped[str] = mapped_column(String(180))
    rows: Mapped[list] = mapped_column(JSON)
    issues: Mapped[list] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(TZ))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Rebate(Base):
    __tablename__ = "approved_rebates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"))
    approved_by: Mapped[str] = mapped_column(String(120))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(TZ))
    reason: Mapped[str] = mapped_column(String(160), default="")


class BillingCycle(Base):
    __tablename__ = "billing_cycles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    unit_id: Mapped[str] = mapped_column(ForeignKey("mess_units.id"), index=True)
    cycle_month: Mapped[str] = mapped_column(String(7), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="preview")
    daily_rate: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(TZ))
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("unit_id", "cycle_month", "version", name="uq_billing_cycle_version"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    record_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(TZ), index=True)


def get_db():
    with SessionLocal() as db:
        yield db


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    result = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2${salt.hex()}${result.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310_000).hex()
        return algorithm == "pbkdf2" and hmac.compare_digest(actual, expected)
    except ValueError:
        return False


def issue_session(kind: str, subject_id: str, role: str) -> str:
    issued = str(int(datetime.now().timestamp()))
    claims = f"{kind}.{subject_id}.{role}.{issued}"
    signature = hmac.new(TOKEN_SECRET, claims.encode(), hashlib.sha256).hexdigest()
    return f"{claims}.{signature}"


def session_claims(authorization: str | None) -> tuple[str, str, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to continue")
    try:
        kind, subject_id, role, issued, signature = authorization[7:].split(".")
        claims = f"{kind}.{subject_id}.{role}.{issued}"
        expected = hmac.new(TOKEN_SECRET, claims.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or int(issued) < int(datetime.now().timestamp()) - 86400:
            raise ValueError
        return kind, subject_id, role
    except (ValueError, TypeError):
        raise HTTPException(401, "Session expired; sign in again")


def active_student(authorization: str | None, db: Session) -> Student:
    kind, sid, _ = session_claims(authorization)
    if kind != "student":
        raise HTTPException(403, "Student login required")
    student = db.get(Student, sid)
    if not student:
        raise HTTPException(401, "Unknown student session")
    return student


def active_staff(authorization: str | None, db: Session, roles: set[str] | None = None) -> StaffUser:
    kind, sid, role = session_claims(authorization)
    if kind != "staff" or (roles and role not in roles):
        raise HTTPException(403, "This action is not allowed for your account")
    staff = db.get(StaffUser, sid)
    if not staff or not staff.is_active or staff.role != role:
        raise HTTPException(401, "Staff account is inactive")
    return staff


def has_allocation(db: Session, student: Student, today: date) -> bool:
    return db.scalar(select(Allocation.id).where(Allocation.student_id == student.id, Allocation.unit_id == student.unit_id, Allocation.start_date <= today, Allocation.end_date >= today)) is not None


def in_local_time(value: datetime) -> datetime:
    return value.replace(tzinfo=TZ) if value.tzinfo is None else value.astimezone(TZ)


def audit(db: Session, actor: str, action: str, record_id: str, details: dict | None = None):
    db.add(AuditLog(actor=actor[:120], action=action[:100], record_id=str(record_id or "")[:80], details=details or {}))


def service_windows(db: Session, unit_id: str, service_date: date) -> list[dict]:
    """Merge recurring meal windows with additions and cancellations for one date."""
    schedules = db.scalars(select(MealSchedule).where(MealSchedule.unit_id == unit_id)).all()
    overrides = db.scalars(select(MealServiceOverride).where(MealServiceOverride.unit_id == unit_id, MealServiceOverride.service_date == service_date)).all()
    by_name = {schedule.meal_type.casefold(): {"meal": schedule.meal_type, "starts_at": schedule.starts_at, "ends_at": schedule.ends_at, "cancelled": False, "source": "default"} for schedule in schedules}
    revisions = db.scalars(select(MealScheduleRevision).where(MealScheduleRevision.unit_id == unit_id, MealScheduleRevision.effective_from <= service_date).order_by(MealScheduleRevision.effective_from.desc())).all()
    applied = set()
    for revision in revisions:
        key = revision.meal_type.casefold()
        if key in by_name and key not in applied:
            by_name[key].update(starts_at=revision.starts_at, ends_at=revision.ends_at)
            applied.add(key)
    for override in overrides:
        by_name[override.meal_type.casefold()] = {"meal": override.meal_type, "starts_at": override.starts_at, "ends_at": override.ends_at, "cancelled": override.is_cancelled, "source": "date"}
    return sorted(by_name.values(), key=lambda item: (item["starts_at"], item["meal"].casefold()))


def meal_state(db: Session, student: Student, now: datetime) -> list[dict]:
    local = now.astimezone(TZ)
    allocated = has_allocation(db, student, local.date())
    result = []
    for schedule in service_windows(db, student.unit_id, local.date()):
        if schedule["cancelled"]:
            continue
        served = db.scalar(select(MealServing.id).where(MealServing.student_id == student.id, MealServing.unit_id == student.unit_id, MealServing.meal_type == schedule["meal"], MealServing.service_date == local.date())) is not None
        in_window = schedule["starts_at"] <= local.timetz().replace(tzinfo=None) <= schedule["ends_at"]
        result.append({"meal": schedule["meal"], "starts_at": schedule["starts_at"].strftime("%H:%M"), "ends_at": schedule["ends_at"].strftime("%H:%M"), "available": bool(allocated and student.photo_key and in_window and not served), "served": served, "allocated": allocated, "needs_photo": not bool(student.photo_key)})
    return result


class LoginInput(BaseModel):
    identifier: str
    password: str


class OTPRequest(BaseModel):
    identifier: str


class OTPVerify(BaseModel):
    challenge_id: str
    code: str = Field(pattern="^[0-9]{6}$")
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class TokenInput(BaseModel):
    meal: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9 &'\-]*$")


class ScheduleInput(BaseModel):
    meal: str = Field(pattern="^(Breakfast|Lunch|Snacks|Dinner)$")
    starts_at: time
    ends_at: time


class ServiceWindowInput(BaseModel):
    service_date: date
    meal: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9 &'\-]*$")
    starts_at: time
    ends_at: time


class MealPlanInput(BaseModel):
    service_date: date
    meal_type: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9 &'\-]*$")
    meal_category: str = Field(default="Veg", pattern="^(Veg|Non-Veg|Jain)$")
    menu: list[str] = Field(min_length=1, max_length=30)


class StaffInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=254)
    role: str = Field(pattern="^(admin|finance)$")
    password: str | None = Field(default=None, min_length=8, max_length=128)


class StudentInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=254)
    phone: str = Field(min_length=7, max_length=20)
    roll_number: str = Field(min_length=2, max_length=64)
    start_date: date
    end_date: date
    gender: str = ""
    course: str = ""
    branch: str = ""


def seed():
    with SessionLocal() as db:
        institution = db.scalar(select(Institution).where(Institution.name == "IIT Jodhpur"))
        if not institution:
            institution = Institution(name="IIT Jodhpur")
            db.add(institution)
            db.flush()
        unit = db.scalar(select(MessUnit).where(MessUnit.institution_id == institution.id))
        if not unit:
            unit = MessUnit(institution_id=institution.id, name="IIT Jodhpur Vegetarian Mess")
            db.add(unit)
            db.flush()
        student = db.scalar(select(Student).where(Student.email == "student@iitj.ac.in"))
        if not student:
            student = Student(institution_id=institution.id, unit_id=unit.id, name="Aarav Sharma", email="student@iitj.ac.in", phone="+910000000001", roll_number="B23CS001", password_hash=hash_password(os.getenv("STUDENT_DEMO_PASSWORD", "demo-student")), password_initialized=True)
            db.add(student)
            db.flush()
        else:
            student.password_initialized = True
        unallocated = db.scalar(select(Student).where(Student.email == "unallocated@iitj.ac.in"))
        if not unallocated:
            db.add(Student(institution_id=institution.id, unit_id=unit.id, name="Neha Demo", email="unallocated@iitj.ac.in", phone="+910000000002", roll_number="B23CS999", password_hash=hash_password(os.getenv("STUDENT_DEMO_PASSWORD", "demo-student")), password_initialized=True))
        first_login = db.scalar(select(Student).where(Student.roll_number == "B23CS000"))
        if not first_login:
            first_login = Student(institution_id=institution.id, unit_id=unit.id, name="Riya Demo", email="firstlogin@iitj.ac.in", phone="+910000000003", roll_number="B23CS000", password_hash=hash_password(secrets.token_urlsafe(24)), password_initialized=False)
            db.add(first_login)
            db.flush()
        today = datetime.now(TZ).date()
        month_start = today.replace(day=1)
        month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if not db.scalar(select(Allocation.id).where(Allocation.student_id == student.id)):
            db.add(Allocation(student_id=student.id, unit_id=unit.id, start_date=month_start, end_date=month_end, source_batch_id="synthetic-demo-seed"))
        if not db.scalar(select(Allocation.id).where(Allocation.student_id == first_login.id)):
            db.add(Allocation(student_id=first_login.id, unit_id=unit.id, start_date=month_start, end_date=month_end, source_batch_id="synthetic-demo-first-login"))
        for meal, start, end in [("Breakfast", "07:30", "10:30"), ("Lunch", "12:00", "14:30"), ("Snacks", "16:30", "18:00"), ("Dinner", "19:30", "22:00")]:
            if not db.scalar(select(MealSchedule.id).where(MealSchedule.unit_id == unit.id, MealSchedule.meal_type == meal)):
                db.add(MealSchedule(unit_id=unit.id, meal_type=meal, starts_at=time.fromisoformat(start), ends_at=time.fromisoformat(end)))
        for email, name, role, env_name, fallback in [
            ("admin@unifeast.local", "UniFeast Demo Admin", "admin", "ADMIN_DEMO_PASSWORD", "demo-admin"),
            ("finance@unifeast.local", "Finance Demo Reviewer", "finance", "FINANCE_DEMO_PASSWORD", "demo-finance"),
        ]:
            if not db.scalar(select(StaffUser.id).where(StaffUser.email == email)):
                db.add(StaffUser(name=name, email=email, role=role, password_hash=hash_password(os.getenv(env_name, fallback)), is_active=True))
        db.commit()


@app.on_event("startup")
def on_startup():
    seed()


@app.get("/health")
def health():
    return {"status": "ok", "service": "iitj-meals"}


@app.post("/api/v1/auth/login")
@app.post("/api/v1/auth/student")
def login(body: LoginInput, db: Session = Depends(get_db)):
    identifier = body.identifier.strip()
    staff = db.scalar(select(StaffUser).where(StaffUser.email == identifier.lower())) if "@" in identifier else None
    if staff:
        if not staff.is_active or not password_matches(body.password, staff.password_hash):
            raise HTTPException(401, "Email or password is incorrect")
        staff.last_login_at = datetime.now(TZ)
        db.commit()
        return {"access_token": issue_session("staff", staff.id, staff.role), "token_type": "bearer", "role": staff.role, "user": {"name": staff.name, "email": staff.email}}
    student = db.scalar(select(Student).where(or_(Student.phone == identifier, Student.roll_number == identifier.upper(), Student.email == identifier.lower())))
    if not student or not student.password_initialized:
        raise HTTPException(403, "Use a one-time code to set up your student password")
    if not password_matches(body.password, student.password_hash):
        raise HTTPException(401, "Phone/ID or password is incorrect")
    return {"access_token": issue_session("student", student.id, "student"), "token_type": "bearer", "role": "student", "user": {"name": student.name, "email": student.email, "roll_number": student.roll_number}}


@app.post("/api/v1/auth/otp/request")
def request_student_otp(body: OTPRequest, db: Session = Depends(get_db)):
    if os.getenv("OTP_MODE", "development") != "development":
        raise HTTPException(503, "No SMS OTP provider is configured for this standalone build")
    identifier = body.identifier.strip()
    student = db.scalar(select(Student).where(or_(Student.phone == identifier, Student.roll_number == identifier.upper(), Student.email == identifier.lower())))
    result = {"message": "If this phone or student ID is registered, a one-time code is ready in local demo mode.", "challenge_id": None, "development_code": None, "delivery": "local-demo"}
    if not student:
        return result
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = OTPChallenge(id=str(uuid.uuid4()), student_id=student.id, code_hash=hmac.new(TOKEN_SECRET, f"{student.id}:{code}".encode(), hashlib.sha256).hexdigest(), expires_at=datetime.now(TZ) + timedelta(minutes=5), attempts=0)
    db.add(challenge)
    db.commit()
    result.update({"challenge_id": challenge.id, "development_code": code})
    return result


@app.post("/api/v1/auth/otp/verify")
def verify_student_otp(body: OTPVerify, db: Session = Depends(get_db)):
    challenge = db.get(OTPChallenge, body.challenge_id)
    now = datetime.now(TZ)
    if not challenge or challenge.used_at or in_local_time(challenge.expires_at) <= now:
        raise HTTPException(410, "Code expired. Request a new one.")
    if challenge.attempts >= 5:
        raise HTTPException(429, "Too many attempts. Request a new code.")
    challenge.attempts += 1
    submitted = hmac.new(TOKEN_SECRET, f"{challenge.student_id}:{body.code}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(submitted, challenge.code_hash):
        db.commit()
        raise HTTPException(401, "That code is not correct")
    student = db.get(Student, challenge.student_id)
    if not student.password_initialized and not body.new_password:
        db.commit()
        raise HTTPException(422, "Create a password to finish your first sign in")
    if body.new_password:
        student.password_hash = hash_password(body.new_password)
        student.password_initialized = True
    challenge.used_at = now
    audit(db, student.id, "student.otp_login", challenge.id)
    db.commit()
    return {"access_token": issue_session("student", student.id, "student"), "token_type": "bearer", "role": "student", "user": {"name": student.name, "email": student.email, "roll_number": student.roll_number}, "first_login": not bool(student.photo_key)}


@app.get("/api/v1/student/me")
def me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    student = active_student(authorization, db)
    return {"id": student.id, "name": student.name, "email": student.email, "roll_number": student.roll_number, "photo_registered": bool(student.photo_key), "mess_unit": db.get(MessUnit, student.unit_id).name, "eligible": has_allocation(db, student, datetime.now(TZ).date())}


@app.post("/api/v1/student/selfie")
def selfie(file: UploadFile = File(...), authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    student = active_student(authorization, db)
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, "Upload a JPEG, PNG, or WebP image")
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Photo must be 5 MB or smaller")
    if not content.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF")):
        raise HTTPException(415, "Image file could not be verified")
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[file.content_type]
    key = f"{uuid.uuid4().hex}.{extension}"
    folder = Path(os.getenv("PHOTO_DIR", "/data/photos"))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / key).write_bytes(content)
    student.photo_key = key
    audit(db, student.id, "student.selfie_registered", key)
    db.commit()
    return {"photo_registered": True}


@app.get("/api/v1/student/photo")
def photo(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    student = active_student(authorization, db)
    if not student.photo_key:
        raise HTTPException(404, "No registered photo")
    path = Path(os.getenv("PHOTO_DIR", "/data/photos")) / student.photo_key
    if not path.is_file():
        raise HTTPException(404, "Photo unavailable")
    return FileResponse(path)


@app.get("/api/v1/student/meals")
def meals(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    student = active_student(authorization, db)
    return {"server_time": datetime.now(TZ).isoformat(), "timezone": "Asia/Kolkata", "meals": meal_state(db, student, datetime.now(TZ))}


@app.post("/api/v1/student/tokens")
def create_token(body: TokenInput, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    student = active_student(authorization, db)
    now = datetime.now(TZ)
    states = {item["meal"]: item for item in meal_state(db, student, now)}
    state = states.get(body.meal)
    if not state:
        raise HTTPException(404, "This meal is not scheduled for today")
    if not state["allocated"]:
        raise HTTPException(403, "You do not have an active allocation for this meal service date")
    if state["needs_photo"]:
        raise HTTPException(403, "Register your selfie before collecting a meal")
    if state["served"]:
        raise HTTPException(409, "This meal has already been served today")
    if not state["available"]:
        raise HTTPException(409, "This meal is outside its configured collection window")
    reference = f"UF-{now:%y%m%d}-{secrets.randbelow(10_000_000_000):010d}"
    unit = db.get(MessUnit, student.unit_id)
    token = MealToken(id=str(uuid.uuid4()), token_hash=digest(reference), reference=reference, student_name_snapshot=student.name,
                      roll_number_snapshot=student.roll_number, unit_name_snapshot=unit.name,
                      student_id=student.id, unit_id=student.unit_id, meal_type=body.meal, service_date=now.date(), created_at=now, expires_at=now + timedelta(minutes=15))
    db.add(token)
    audit(db, student.id, "meal.token_created", token.id, {"meal": body.meal, "unit_id": student.unit_id})
    db.commit()
    return {"token": reference, "meal": body.meal, "student_name": student.name, "roll_number": student.roll_number, "mess_unit": unit.name, "date": now.strftime("%d %B %Y"), "server_timestamp": now.isoformat(), "expires_at": token.expires_at.isoformat(), "ttl_seconds": 900, "status": "pending", "photo_registered": bool(student.photo_key)}


@app.get("/api/v1/student/tokens/{raw}")
def token_status(raw: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    student = active_student(authorization, db)
    token = db.scalar(select(MealToken).where(MealToken.token_hash == digest(raw), MealToken.student_id == student.id))
    if not token:
        raise HTTPException(404, "Token not found")
    now = datetime.now(TZ)
    return {"status": "served" if token.redeemed_at else "expired" if in_local_time(token.expires_at) <= now else "pending", "served_at": token.redeemed_at.isoformat() if token.redeemed_at else None}


@app.post("/api/v1/student/tokens/{raw}/collect")
def confirm_collection(raw: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    student = active_student(authorization, db)
    token = db.scalar(select(MealToken).where(MealToken.token_hash == digest(raw), MealToken.student_id == student.id).with_for_update())
    if not token:
        raise HTTPException(404, "Meal reference not found")
    now = datetime.now(TZ)
    if token.redeemed_at:
        raise HTTPException(409, "This meal has already been marked collected")
    if in_local_time(token.expires_at) <= now or token.service_date != now.date():
        raise HTTPException(410, "Meal reference expired. Request a new one.")
    if not has_allocation(db, student, now.date()):
        raise HTTPException(403, "Your allocation is no longer active")
    if not any(item["meal"] == token.meal_type and not item["cancelled"] for item in service_windows(db, token.unit_id, token.service_date)):
        raise HTTPException(409, "This meal has been removed from today's schedule")
    # Tokens created before the reporting migration can still be completed.
    token.reference = token.reference or raw
    token.student_name_snapshot = token.student_name_snapshot or student.name
    token.roll_number_snapshot = token.roll_number_snapshot or student.roll_number
    token.unit_name_snapshot = token.unit_name_snapshot or db.get(MessUnit, token.unit_id).name
    token.redeemed_at = now
    db.add(MealServing(student_id=student.id, unit_id=student.unit_id, meal_type=token.meal_type, service_date=token.service_date, served_at=now, collection_source="student-slide", token_id=token.id))
    audit(db, student.id, "meal.collected_by_student", token.id, {"meal": token.meal_type, "unit_id": student.unit_id})
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "This meal has already been marked collected")
    return {"status": "collected", "meal": token.meal_type, "collected_at": now.isoformat()}


@app.get("/api/v1/admin/schedules")
def list_schedules(x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    return [{"meal": s.meal_type, "starts_at": s.starts_at.strftime("%H:%M"), "ends_at": s.ends_at.strftime("%H:%M")} for s in db.scalars(select(MealSchedule)).all()]


@app.put("/api/v1/admin/schedules")
def update_schedule(body: ScheduleInput, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor_id = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    if body.ends_at <= body.starts_at:
        raise HTTPException(422, "End time must be later than start time")
    schedule = db.scalar(select(MealSchedule).where(MealSchedule.meal_type == body.meal))
    if not schedule:
        raise HTTPException(404, "Meal schedule not found")
    today = datetime.now(TZ).date()
    existing = db.scalars(select(MealScheduleRevision).where(MealScheduleRevision.unit_id == schedule.unit_id, MealScheduleRevision.meal_type == schedule.meal_type)).all()
    if not existing:
        db.add(MealScheduleRevision(unit_id=schedule.unit_id, meal_type=schedule.meal_type, effective_from=date.min, starts_at=schedule.starts_at, ends_at=schedule.ends_at))
    current = next((revision for revision in existing if revision.effective_from == today), None)
    if current:
        current.starts_at, current.ends_at = body.starts_at, body.ends_at
    else:
        db.add(MealScheduleRevision(unit_id=schedule.unit_id, meal_type=schedule.meal_type, effective_from=today, starts_at=body.starts_at, ends_at=body.ends_at))
    schedule.starts_at, schedule.ends_at = body.starts_at, body.ends_at
    audit(db, actor_id, "meal.schedule_updated", str(schedule.id), {"meal": body.meal, "starts_at": body.starts_at.isoformat(), "ends_at": body.ends_at.isoformat()})
    db.commit()
    return {"meal": body.meal, "starts_at": body.starts_at.strftime("%H:%M"), "ends_at": body.ends_at.strftime("%H:%M")}


@app.get("/api/v1/admin/service-windows")
def admin_service_windows(service_date: date, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    unit = db.scalar(select(MessUnit).limit(1))
    return [{**item, "starts_at": item["starts_at"].strftime("%H:%M"), "ends_at": item["ends_at"].strftime("%H:%M")}
            for item in service_windows(db, unit.id, service_date)]


def save_service_window(body: ServiceWindowInput, creating: bool, actor: str, db: Session) -> dict:
    if body.service_date < datetime.now(TZ).date():
        raise HTTPException(422, "Past meal service windows cannot be changed")
    if body.ends_at <= body.starts_at:
        raise HTTPException(422, "End time must be later than start time")
    unit = db.scalar(select(MessUnit).limit(1))
    existing = next((item for item in service_windows(db, unit.id, body.service_date) if item["meal"].casefold() == body.meal.casefold()), None)
    if creating and existing:
        raise HTTPException(409, "This meal already exists for the selected date; edit or restore it instead")
    if not creating and not existing:
        raise HTTPException(404, "Meal service window not found for this date")
    name = existing["meal"] if existing else body.meal.strip()
    override = db.scalar(select(MealServiceOverride).where(MealServiceOverride.unit_id == unit.id, MealServiceOverride.service_date == body.service_date, func.lower(MealServiceOverride.meal_type) == name.lower()))
    if not override:
        override = MealServiceOverride(unit_id=unit.id, service_date=body.service_date, meal_type=name, starts_at=body.starts_at, ends_at=body.ends_at, is_cancelled=False)
        db.add(override)
    override.starts_at, override.ends_at, override.is_cancelled = body.starts_at, body.ends_at, False
    db.flush()
    audit(db, actor, "meal.service_window_saved", str(override.id), {"date": body.service_date.isoformat(), "meal": name, "starts_at": body.starts_at.isoformat(), "ends_at": body.ends_at.isoformat()})
    db.commit()
    return {"meal": name, "service_date": body.service_date.isoformat(), "starts_at": body.starts_at.strftime("%H:%M"), "ends_at": body.ends_at.strftime("%H:%M"), "cancelled": False}


@app.post("/api/v1/admin/service-windows")
def add_service_window(body: ServiceWindowInput, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    return save_service_window(body, True, actor, db)


@app.put("/api/v1/admin/service-windows")
def edit_service_window(body: ServiceWindowInput, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    return save_service_window(body, False, actor, db)


@app.delete("/api/v1/admin/service-windows")
def remove_service_window(service_date: date, meal: str = Query(min_length=1, max_length=20), x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    if service_date < datetime.now(TZ).date():
        raise HTTPException(422, "Past meal service windows cannot be changed")
    unit = db.scalar(select(MessUnit).limit(1))
    existing = next((item for item in service_windows(db, unit.id, service_date) if item["meal"].casefold() == meal.casefold()), None)
    if not existing or existing["cancelled"]:
        raise HTTPException(404, "Active meal service window not found for this date")
    override = db.scalar(select(MealServiceOverride).where(MealServiceOverride.unit_id == unit.id, MealServiceOverride.service_date == service_date, func.lower(MealServiceOverride.meal_type) == existing["meal"].lower()))
    if not override:
        override = MealServiceOverride(unit_id=unit.id, service_date=service_date, meal_type=existing["meal"], starts_at=existing["starts_at"], ends_at=existing["ends_at"], is_cancelled=True)
        db.add(override)
    override.is_cancelled = True
    db.flush()
    audit(db, actor, "meal.service_window_removed", str(override.id), {"date": service_date.isoformat(), "meal": existing["meal"]})
    db.commit()
    return {"meal": existing["meal"], "service_date": service_date.isoformat(), "cancelled": True}


@app.get("/api/v1/admin/summary")
def admin_summary(x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor_id = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    today = datetime.now(TZ).date()
    active = len(set(db.scalars(select(Allocation.student_id).where(Allocation.start_date <= today, Allocation.end_date >= today)).all()))
    return {"active_allocations": active,
            "served_today": len(db.scalars(select(MealServing).where(MealServing.service_date == today)).all()),
            "schedules": list_schedules(x_admin_key, db), "billing_status": "Available", "rebates_status": "Available"}


@app.get("/api/v1/admin/units")
def admin_units(x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    today = datetime.now(TZ).date()
    result = []
    for unit in db.scalars(select(MessUnit).order_by(MessUnit.name)).all():
        students = set(db.scalars(select(Allocation.student_id).where(Allocation.unit_id == unit.id, Allocation.start_date <= today, Allocation.end_date >= today)).all())
        result.append({"id": unit.id, "name": unit.name, "capacity": unit.capacity, "students": len(students), "occupancy_percent": round(100 * len(students) / unit.capacity) if unit.capacity else None})
    return result


@app.put("/api/v1/admin/units/{unit_id}/capacity")
def update_unit_capacity(unit_id: str, capacity: int = Query(ge=0, le=100000), x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    unit = db.get(MessUnit, unit_id)
    if not unit:
        raise HTTPException(404, "Mess unit not found")
    unit.capacity = capacity
    audit(db, actor, "unit.capacity_updated", unit.id, {"capacity": capacity})
    db.commit()
    return {"unit_id": unit.id, "capacity": unit.capacity}


@app.get("/api/v1/admin/meal-plans")
def meal_plans(start: date, end: date, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    if start > end or (end - start).days > 42:
        raise HTTPException(422, "Choose up to six weeks of meal plans")
    return [{"id": p.id, "date": p.service_date.isoformat(), "meal": p.meal_type, "category": p.meal_category, "menu": p.menu, "active": p.is_active, "created_by": p.created_by, "created_at": in_local_time(p.created_at).isoformat()}
            for p in db.scalars(select(MealPlan).where(MealPlan.service_date >= start, MealPlan.service_date <= end).order_by(MealPlan.service_date, MealPlan.meal_type)).all()]


@app.put("/api/v1/admin/meal-plans")
def save_meal_plan(body: MealPlanInput, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    unit = db.scalar(select(MessUnit).limit(1))
    plan = db.scalar(select(MealPlan).where(MealPlan.unit_id == unit.id, MealPlan.service_date == body.service_date, MealPlan.meal_type == body.meal_type))
    if not plan:
        plan = MealPlan(unit_id=unit.id, service_date=body.service_date, meal_type=body.meal_type, menu=[], created_by=actor)
        db.add(plan)
    plan.menu = [item.strip()[:120] for item in body.menu if item.strip()]
    if not plan.menu:
        raise HTTPException(422, "Add at least one menu item")
    plan.meal_category, plan.is_active = body.meal_category, True
    audit(db, actor, "meal.plan_saved", plan.id, {"date": body.service_date.isoformat(), "meal": body.meal_type})
    db.commit()
    return {"id": plan.id, "date": plan.service_date.isoformat(), "meal": plan.meal_type, "category": plan.meal_category, "menu": plan.menu, "active": plan.is_active, "created_by": plan.created_by, "created_at": in_local_time(plan.created_at).isoformat()}


@app.patch("/api/v1/admin/meal-plans/{plan_id}/status")
def set_meal_plan_status(plan_id: str, active: bool, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    plan = db.get(MealPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Menu plan not found")
    plan.is_active = active
    audit(db, actor, "meal.plan_status_changed", plan.id, {"active": active})
    db.commit()
    return {"id": plan.id, "active": plan.is_active}


@app.get("/api/v1/admin/users")
def admin_users(active: bool | None = None, logged_in: bool = False, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    query = select(StaffUser).order_by(StaffUser.name)
    if active is not None:
        query = query.where(StaffUser.is_active == active)
    if logged_in:
        query = query.where(StaffUser.last_login_at >= datetime.now(TZ) - timedelta(days=1))
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role, "active": u.is_active, "last_login_at": in_local_time(u.last_login_at).isoformat() if u.last_login_at else None} for u in db.scalars(query).all()]


@app.post("/api/v1/admin/users")
def create_admin_user(body: StaffInput, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    if not body.password:
        raise HTTPException(422, "A temporary password of at least 8 characters is required")
    email = body.email.lower().strip()
    if db.scalar(select(StaffUser.id).where(StaffUser.email == email)):
        raise HTTPException(409, "A staff account already uses this email")
    user = StaffUser(name=body.name.strip(), email=email, role=body.role, password_hash=hash_password(body.password), is_active=True)
    db.add(user)
    db.flush()
    audit(db, actor, "staff.created", user.id, {"role": user.role, "email": user.email})
    db.commit()
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "active": user.is_active}


@app.patch("/api/v1/admin/users/{user_id}")
def update_admin_user(user_id: str, body: StaffInput, active: bool | None = None, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    user = db.get(StaffUser, user_id)
    if not user:
        raise HTTPException(404, "Staff account not found")
    if body.email.strip().lower() != user.email and db.scalar(select(StaffUser.id).where(StaffUser.email == body.email.strip().lower())):
        raise HTTPException(409, "A staff account already uses this email")
    user.name, user.email, user.role = body.name.strip(), body.email.strip().lower(), body.role
    if body.password:
        user.password_hash = hash_password(body.password)
    if active is not None:
        _, actor_id, _ = session_claims(f"Bearer {x_admin_key}")
        if user.id == actor_id and not active:
            raise HTTPException(422, "You cannot deactivate your own account")
        user.is_active = active
    audit(db, actor, "staff.updated", user.id, {"role": user.role, "active": user.is_active})
    db.commit()
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "active": user.is_active}


@app.get("/api/v1/admin/students")
def admin_students(q: str = Query(default="", max_length=120), x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    query = select(Student).order_by(Student.name)
    if q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(or_(Student.name.ilike(needle), Student.roll_number.ilike(needle), Student.email.ilike(needle), Student.phone.ilike(needle), Student.course.ilike(needle), Student.branch.ilike(needle)))
    today = datetime.now(TZ).date()
    rows = db.scalars(query.limit(5000)).all()
    allocations = db.scalars(select(Allocation).where(Allocation.student_id.in_([s.id for s in rows]))).all() if rows else []
    periods = {}
    for allocation in allocations:
        item = periods.setdefault(allocation.student_id, {"start": allocation.start_date, "end": allocation.end_date})
        item["start"] = min(item["start"], allocation.start_date)
        item["end"] = max(item["end"], allocation.end_date)
    return [{"name": s.name, "roll_number": s.roll_number, "email": s.email, "phone": s.phone,
             "active": has_allocation(db, s, today), "unit": db.get(MessUnit, s.unit_id).name if db.get(MessUnit, s.unit_id) else "—",
             "gender": s.gender or "", "course": s.course or "", "branch": s.branch or "",
             "allocation_start": periods[s.id]["start"].isoformat() if s.id in periods else "", "allocation_end": periods[s.id]["end"].isoformat() if s.id in periods else ""} for s in rows]


@app.post("/api/v1/admin/students")
def create_student(body: StudentInput, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    actor = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    if body.end_date < body.start_date:
        raise HTTPException(422, "Allocation end date must be on or after its start date")
    email, roll, phone = body.email.strip().lower(), body.roll_number.strip().upper(), body.phone.strip()
    if "@" not in email or db.scalar(select(Student.id).where(or_(Student.email == email, Student.roll_number == roll, Student.phone == phone))):
        raise HTTPException(409, "Check the email, roll number, and phone; one may already be registered")
    unit = db.scalar(select(MessUnit).limit(1))
    institution = db.get(Institution, unit.institution_id)
    student = Student(institution_id=institution.id, unit_id=unit.id, name=body.name.strip(), email=email, phone=phone,
                      roll_number=roll, password_hash=hash_password(secrets.token_urlsafe(24)), password_initialized=False,
                      gender=body.gender or None, course=body.course or None, branch=body.branch or None)
    db.add(student)
    db.flush()
    db.add(Allocation(student_id=student.id, unit_id=unit.id, start_date=body.start_date, end_date=body.end_date, source_batch_id="admin-single-entry"))
    audit(db, actor, "student.created", student.id, {"roll_number": roll})
    db.commit()
    return {"id": student.id, "name": student.name, "roll_number": roll, "status": "created"}


@app.get("/api/v1/admin/analytics")
def admin_analytics(start: date | None = None, end: date | None = None, course: str | None = None, branch: str | None = None, roll_number: str | None = None, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    end = end or datetime.now(TZ).date()
    start = start or end - timedelta(days=29)
    if start > end or (end - start).days > 366:
        raise HTTPException(422, "Choose a valid range of up to 367 days")
    query = select(MealServing).join(Student, MealServing.student_id == Student.id).where(MealServing.service_date >= start, MealServing.service_date <= end)
    if course: query = query.where(Student.course == course)
    if branch: query = query.where(Student.branch == branch)
    if roll_number: query = query.where(Student.roll_number == roll_number)
    servings = db.scalars(query.order_by(MealServing.service_date)).all()
    by_day, by_meal, by_day_meal = {}, {}, {}
    for row in servings:
        key = row.service_date.isoformat()
        by_day[key] = by_day.get(key, 0) + 1
        by_meal[row.meal_type] = by_meal.get(row.meal_type, 0) + 1
        by_day_meal.setdefault(key, {})[row.meal_type] = by_day_meal.setdefault(key, {}).get(row.meal_type, 0) + 1
    rebate_query = select(Rebate).join(Student, Rebate.student_id == Student.id).where(Rebate.start_date <= end, Rebate.end_date >= start)
    if course: rebate_query = rebate_query.where(Student.course == course)
    if branch: rebate_query = rebate_query.where(Student.branch == branch)
    if roll_number: rebate_query = rebate_query.where(Student.roll_number == roll_number)
    rebates = db.scalars(rebate_query).all()
    rebate_students = len({r.student_id for r in rebates})
    rebate_weekdays, rebate_reasons = {}, {}
    rebate_requests = pending_rebate_requests = 0
    request_batches = db.scalars(select(ImportBatch).where(ImportBatch.kind == "rebate", ImportBatch.status.in_(["pending_approval", "approved", "rejected"]))).all()
    for batch in request_batches:
        for request in batch.rows:
            request_start, request_end = date.fromisoformat(request["start_date"]), date.fromisoformat(request["end_date"])
            if request_start > end or request_end < start:
                continue
            rebate_requests += 1
            if batch.status == "pending_approval":
                pending_rebate_requests += 1
            weekday = request_start.strftime("%A")
            rebate_weekdays[weekday] = rebate_weekdays.get(weekday, 0) + 1
            reason = (request.get("reason") or "").strip() or "Not specified"
            rebate_reasons[reason] = rebate_reasons.get(reason, 0) + 1
    active_query = select(Allocation.student_id).join(Student, Allocation.student_id == Student.id).where(Allocation.start_date <= end, Allocation.end_date >= end)
    if course: active_query = active_query.where(Student.course == course)
    if branch: active_query = active_query.where(Student.branch == branch)
    if roll_number: active_query = active_query.where(Student.roll_number == roll_number)
    active_ids = set(db.scalars(active_query).all())
    active = len(active_ids)
    demographics = {"gender": {}, "course": {}, "branch": {}}
    active_students = db.scalars(select(Student).where(Student.id.in_(active_ids))).all() if active_ids else []
    for student in active_students:
        for key, value in (("gender", student.gender), ("course", student.course), ("branch", student.branch)):
            label = value or "Not specified"
            demographics[key][label] = demographics[key].get(label, 0) + 1
    return {"start": start.isoformat(), "end": end.isoformat(), "active_students": active,
            "meals_served": len(servings), "students_served": len({r.student_id for r in servings}),
            "rebate_periods": len(rebates), "rebate_requests": rebate_requests, "pending_rebate_requests": pending_rebate_requests, "students_on_rebate": rebate_students,
            "by_day": [{"date": k, "meals": v, "by_meal": by_day_meal.get(k, {})} for k, v in sorted(by_day.items())], "by_meal": by_meal,
            "rebate_frequency_by_weekday": rebate_weekdays, "rebate_reasons": rebate_reasons, "demographics": demographics}


PRESENCE_FIELDS = ["date", "meal", "roll_number", "student_name", "mess", "status", "token_reference", "token_created_at", "token_expires_at", "collected_at", "collection_source"]


def presence_rows(db: Session, start: date, end: date, meal: str | None, course: str | None, branch: str | None, roll_number: str | None):
    """Yield allocation-based statuses and confirmed collection details in mess time."""
    if start > end or (end - start).days > 30:
        raise HTTPException(422, "Choose a valid presence report range of up to 31 days")
    query = select(Student, Allocation).join(Allocation, Allocation.student_id == Student.id).where(Allocation.start_date <= end, Allocation.end_date >= start)
    if course: query = query.where(Student.course == course)
    if branch: query = query.where(Student.branch == branch)
    if roll_number: query = query.where(Student.roll_number == roll_number.strip().upper())
    allocations = db.execute(query).all()
    people = {}
    for student, allocation in allocations:
        key = (student.id, allocation.unit_id)
        entry = people.setdefault(key, {"student": student, "periods": []})
        entry["periods"].append((allocation.start_date, allocation.end_date))
    if not people:
        return
    student_ids = {key[0] for key in people}
    unit_ids = {key[1] for key in people}
    units = {unit.id: unit for unit in db.scalars(select(MessUnit).where(MessUnit.id.in_(unit_ids))).all()}
    servings = db.scalars(select(MealServing).where(MealServing.student_id.in_(student_ids), MealServing.unit_id.in_(unit_ids), MealServing.service_date >= start, MealServing.service_date <= end)).all()
    served = {(row.student_id, row.unit_id, row.service_date, row.meal_type): row for row in servings}
    tokens = db.scalars(select(MealToken).where(MealToken.student_id.in_(student_ids), MealToken.unit_id.in_(unit_ids), MealToken.service_date >= start, MealToken.service_date <= end, MealToken.redeemed_at.is_not(None))).all()
    token_by_id = {token.id: token for token in tokens}
    legacy_tokens = {}
    for token in tokens:
        key = (token.student_id, token.unit_id, token.service_date, token.meal_type, in_local_time(token.redeemed_at))
        legacy_tokens.setdefault(key, []).append(token)
    rebate_rows = db.scalars(select(Rebate).where(Rebate.student_id.in_(student_ids), Rebate.unit_id.in_(unit_ids), Rebate.start_date <= end, Rebate.end_date >= start)).all()
    rebates = {}
    for rebate in rebate_rows:
        rebates.setdefault((rebate.student_id, rebate.unit_id), []).append((rebate.start_date, rebate.end_date))
    now = datetime.now(TZ)
    ordered_people = sorted(people.items(), key=lambda item: (item[1]["student"].name.casefold(), item[1]["student"].roll_number))
    for day_offset in range((end - start).days, -1, -1):
        day = start + timedelta(days=day_offset)
        windows = {unit_id: service_windows(db, unit_id, day) for unit_id in unit_ids}
        for (student_id, unit_id), entry in ordered_people:
            if not any(first <= day <= last for first, last in entry["periods"]):
                continue
            student = entry["student"]
            for window in windows[unit_id]:
                if meal and window["meal"].casefold() != meal.casefold():
                    continue
                serving = served.get((student_id, unit_id, day, window["meal"]))
                if window["cancelled"] and not serving:
                    continue
                token = token_by_id.get(serving.token_id) if serving and serving.token_id else None
                if serving and not token:
                    candidates = legacy_tokens.get((student_id, unit_id, day, window["meal"], in_local_time(serving.served_at)), [])
                    token = candidates[0] if len(candidates) == 1 else None
                if serving:
                    status = "Collected"
                elif any(first <= day <= last for first, last in rebates.get((student_id, unit_id), [])):
                    status = "On rebate"
                elif day > now.date() or (day == now.date() and now.timetz().replace(tzinfo=None) <= window["ends_at"]):
                    status = "Pending"
                else:
                    status = "Not recorded"
                yield {
                    "date": day.isoformat(), "meal": window["meal"],
                    "roll_number": token.roll_number_snapshot if token and token.roll_number_snapshot else student.roll_number,
                    "student_name": token.student_name_snapshot if token and token.student_name_snapshot else student.name,
                    "mess": token.unit_name_snapshot if token and token.unit_name_snapshot else units[unit_id].name,
                    "status": status, "token_reference": token.reference if token else None,
                    "token_created_at": in_local_time(token.created_at).isoformat() if token else None,
                    "token_expires_at": in_local_time(token.expires_at).isoformat() if token else None,
                    "collected_at": in_local_time(serving.served_at).isoformat() if serving else None,
                    "collection_source": serving.collection_source if serving else None,
                }


@app.get("/api/v1/admin/presence")
def admin_presence(start: date, end: date, meal: str | None = None, course: str | None = None, branch: str | None = None, roll_number: str | None = None,
                   status: str | None = Query(default=None, pattern="^(Collected|Not recorded|Pending|On rebate)$"),
                   offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=200),
                   x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    records, counts, total = [], {"Collected": 0, "Not recorded": 0, "Pending": 0, "On rebate": 0}, 0
    for record in presence_rows(db, start, end, meal, course, branch, roll_number):
        counts[record["status"]] += 1
        if status and record["status"] != status:
            continue
        if offset <= total < offset + limit:
            records.append(record)
        total += 1
    return {"records": records, "total": total, "offset": offset, "limit": limit, "counts": counts, "timezone": "Asia/Kolkata"}


@app.get("/api/v1/admin/presence.csv")
def admin_presence_csv(start: date, end: date, meal: str | None = None, course: str | None = None, branch: str | None = None, roll_number: str | None = None,
                       status: str | None = Query(default=None, pattern="^(Collected|Not recorded|Pending|On rebate)$"),
                       x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(PRESENCE_FIELDS)
    for record in presence_rows(db, start, end, meal, course, branch, roll_number):
        if not status or record["status"] == status:
            cells = [record[field] or "" for field in PRESENCE_FIELDS]
            writer.writerow(["'" + cell if isinstance(cell, str) and cell.lstrip().startswith(('=', '+', '-', '@')) else cell for cell in cells])
    from fastapi.responses import StreamingResponse
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=unifeast-presence-{start}-{end}.csv"})


@app.get("/api/v1/admin/mis.csv")
def admin_mis_csv(month: str, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    start, end = month_bounds(month)
    unit = db.scalar(select(MessUnit).limit(1))
    allocations = db.scalars(select(Allocation).where(Allocation.unit_id == unit.id, Allocation.start_date <= end, Allocation.end_date >= start)).all()
    unique_students = {a.student_id for a in allocations}
    servings = db.scalars(select(MealServing).where(MealServing.unit_id == unit.id, MealServing.service_date >= start, MealServing.service_date <= end)).all()
    rebates = db.scalars(select(Rebate).where(Rebate.unit_id == unit.id, Rebate.start_date <= end, Rebate.end_date >= start)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["IIT Jodhpur Mess MIS", month])
    writer.writerow(["Mess", unit.name])
    writer.writerow(["Capacity", unit.capacity])
    writer.writerow(["Allocated students", len(unique_students)])
    writer.writerow(["Occupancy rate", f"{(100 * len(unique_students) / unit.capacity):.1f}%" if unit.capacity else "Not configured"])
    writer.writerow(["Confirmed meals served", len(servings)])
    writer.writerow(["Approved rebate periods", len(rebates)])
    writer.writerow([])
    meal_columns = ["Breakfast", "Lunch", "Snacks", "Dinner"]
    meal_columns += sorted({row.meal_type for row in servings} - set(meal_columns))
    writer.writerow(["Date", *meal_columns, "Total"])
    counts = {}
    for row in servings:
        counts.setdefault(row.service_date.isoformat(), {}).setdefault(row.meal_type, 0)
        counts[row.service_date.isoformat()][row.meal_type] += 1
    for day in sorted(counts):
        meals = counts[day]
        writer.writerow([day, *(meals.get(meal, 0) for meal in meal_columns), sum(meals.values())])
    from fastapi.responses import StreamingResponse
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=unifeast-mis-{month}.csv"})


def require_key(supplied: str | None, env_name: str, fallback: str, message: str, db: Session) -> str:
    if not supplied:
        raise HTTPException(401, message)
    kind, subject_id, role = session_claims(f"Bearer {supplied}")
    expected_role = "finance" if "FINANCE" in env_name else "admin"
    if kind != "staff" or role != expected_role:
        raise HTTPException(403, message)
    user = db.get(StaffUser, subject_id)
    if not user or not user.is_active or user.role != role:
        raise HTTPException(401, "Staff account is inactive")
    return subject_id


def parse_csv(file: UploadFile, content: bytes, required: set[str]) -> list[dict]:
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "CSV must be 5 MB or smaller")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV must use UTF-8 encoding")
    headers = {h.strip().lower() for h in (reader.fieldnames or []) if h}
    if not required.issubset(headers):
        raise HTTPException(422, f"CSV needs these columns: {', '.join(sorted(required))}")
    normalized = []
    for row in reader:
        normalized.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})
    if not normalized:
        raise HTTPException(422, "CSV contains no data rows")
    return normalized


def month_bounds(month: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(month + "-01")
    except ValueError:
        raise HTTPException(422, "Month must use YYYY-MM format")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return start, end


@app.post("/api/v1/admin/allocations/preview")
def allocation_preview(file: UploadFile = File(...), x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    rows = parse_csv(file, file.file.read(5 * 1024 * 1024 + 1), {"name", "email", "phone", "roll_number", "start_date", "end_date"})
    issues, valid, seen_email, seen_roll, seen_phone = [], [], set(), set(), set()
    for number, row in enumerate(rows, start=2):
        try:
            email, roll, name, phone = row["email"].lower(), row["roll_number"], row["name"], row["phone"]
            start, end = date.fromisoformat(row["start_date"]), date.fromisoformat(row["end_date"])
            if "@" not in email or "." not in email.rsplit("@", 1)[-1] or not name or not roll or not phone:
                raise ValueError("name, email, phone and roll_number must be valid")
            if end < start:
                raise ValueError("end_date precedes start_date")
            if len(phone) < 7 or len(phone) > 20:
                raise ValueError("phone must contain 7 to 20 characters")
            if email in seen_email or roll in seen_roll or phone in seen_phone:
                raise ValueError("duplicate email, roll number or phone in this file")
            seen_email.add(email)
            seen_roll.add(roll)
            seen_phone.add(phone)
            conflicts = db.scalars(select(Student).where(or_(Student.email == email, Student.roll_number == roll, Student.phone == phone))).all()
            existing = next((s for s in conflicts if s.roll_number == roll), None)
            if any(s.id != (existing.id if existing else None) for s in conflicts):
                raise ValueError("email, phone and roll number conflict with an existing student")
            if existing and db.scalar(select(Allocation.id).where(Allocation.student_id == existing.id, Allocation.unit_id == existing.unit_id, Allocation.start_date <= end, Allocation.end_date >= start)):
                raise ValueError("allocation period overlaps an existing allocation")
            valid.append({"name": name, "email": email, "phone": phone, "roll_number": roll, "start_date": start.isoformat(), "end_date": end.isoformat(),
                          "gender": row.get("gender", "")[:24], "course": row.get("course", "")[:120], "branch": row.get("branch", "")[:120]})
        except (ValueError, KeyError) as error:
            issues.append({"row": number, "message": str(error)})
    if not valid:
        raise HTTPException(422, {"message": "No valid allocation rows", "issues": issues})
    unit_id = db.scalar(select(MessUnit.id).limit(1))
    prev_start = min(date.fromisoformat(r["start_date"]) for r in valid)
    previous = db.scalars(select(Allocation).where(Allocation.unit_id == unit_id, Allocation.start_date < prev_start, Allocation.end_date >= prev_start - timedelta(days=35))).all()
    prev_students = {a.student_id: db.get(Student, a.student_id) for a in previous}
    incoming_rolls = {r["roll_number"] for r in valid}
    previous_rolls = {s.roll_number for s in prev_students.values() if s}
    existing_by_roll = {s.roll_number: s for s in db.scalars(select(Student).where(Student.roll_number.in_(incoming_rolls))).all()}
    changed = [r["roll_number"] for r in valid if r["roll_number"] in previous_rolls and r["roll_number"] in existing_by_roll and (existing_by_roll[r["roll_number"]].email != r["email"] or existing_by_roll[r["roll_number"]].phone != r["phone"] or existing_by_roll[r["roll_number"]].name != r["name"])]
    summary = {"rows": len(rows), "valid": len(valid), "invalid": len(issues), "added": len(incoming_rolls - previous_rolls), "removed": len(previous_rolls - incoming_rolls), "changed": len(changed), "changed_roll_numbers": changed, "removed_roll_numbers": sorted(previous_rolls - incoming_rolls)}
    batch = ImportBatch(id=str(uuid.uuid4()), kind="allocation", status="preview", source_name=(file.filename or "allocation.csv")[:180], rows=valid, issues=issues, summary=summary)
    db.add(batch)
    audit(db, "demo-site-admin", "allocation.previewed", batch.id, summary)
    db.commit()
    return {"batch_id": batch.id, "status": batch.status, "summary": summary, "issues": issues, "confirmation_required": True, "can_confirm": not issues}


@app.post("/api/v1/admin/allocations/{batch_id}/confirm")
def allocation_confirm(batch_id: str, confirm: bool = False, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    batch = db.get(ImportBatch, batch_id)
    if not batch or batch.kind != "allocation":
        raise HTTPException(404, "Allocation import not found")
    if not confirm:
        raise HTTPException(400, "Set confirm=true after reviewing the preview")
    if batch.status != "preview" or batch.issues:
        raise HTTPException(409, "Only a clean, unconfirmed preview can be imported")
    unit = db.scalar(select(MessUnit).limit(1))
    institution = db.get(Institution, unit.institution_id)
    for row in batch.rows:
        student = db.scalar(select(Student).where(Student.roll_number == row["roll_number"]))
        if student:
            email_owner = db.scalar(select(Student).where(Student.email == row["email"], Student.id != student.id))
            phone_owner = db.scalar(select(Student).where(Student.phone == row["phone"], Student.id != student.id))
            if student.unit_id != unit.id or email_owner or phone_owner:
                raise HTTPException(409, f"Student details changed after preview: {row['roll_number']}")
            student.name, student.email, student.phone = row["name"], row["email"], row["phone"]
            for field in ("gender", "course", "branch"):
                if row.get(field):
                    setattr(student, field, row[field])
        else:
            student = Student(institution_id=institution.id, unit_id=unit.id, name=row["name"], email=row["email"], roll_number=row["roll_number"], phone=row["phone"], password_hash=hash_password(secrets.token_urlsafe(24)), gender=row.get("gender") or None, course=row.get("course") or None, branch=row.get("branch") or None)
            db.add(student)
            db.flush()
        db.add(Allocation(student_id=student.id, unit_id=unit.id, start_date=date.fromisoformat(row["start_date"]), end_date=date.fromisoformat(row["end_date"]), source_batch_id=batch.id))
    batch.status, batch.confirmed_at = "confirmed", datetime.now(TZ)
    audit(db, "demo-site-admin", "allocation.confirmed", batch.id, {"students_imported": len(batch.rows)})
    db.commit()
    return {"batch_id": batch.id, "status": batch.status, "students_imported": len(batch.rows), "summary": batch.summary}


@app.get("/api/v1/admin/allocations/history")
def allocation_history(x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    return [{"batch_id": b.id, "status": b.status, "source_name": b.source_name, "created_at": b.created_at.isoformat(), "confirmed_at": b.confirmed_at.isoformat() if b.confirmed_at else None, "summary": b.summary} for b in db.scalars(select(ImportBatch).where(ImportBatch.kind == "allocation").order_by(ImportBatch.created_at.desc())).all()]


@app.post("/api/v1/admin/rebates/preview")
def rebate_preview(file: UploadFile = File(...), x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    rows = parse_csv(file, file.file.read(5 * 1024 * 1024 + 1), {"roll_number", "start_date", "end_date"})
    issues, valid, seen, intervals = [], [], set(), {}
    for number, row in enumerate(rows, start=2):
        try:
            student = db.scalar(select(Student).where(Student.roll_number == row["roll_number"]))
            start, end = date.fromisoformat(row["start_date"]), date.fromisoformat(row["end_date"])
            if not student:
                raise ValueError("roll number is not registered")
            if end < start:
                raise ValueError("end_date precedes start_date")
            key = (student.id, start, end)
            if key in seen or any(old_start <= end and old_end >= start for old_start, old_end in intervals.get(student.id, [])):
                raise ValueError("rebate periods overlap in this file")
            overlaps = db.scalar(select(Rebate.id).where(Rebate.student_id == student.id, Rebate.start_date <= end, Rebate.end_date >= start))
            if overlaps:
                raise ValueError("period overlaps an already approved rebate")
            seen.add(key)
            intervals.setdefault(student.id, []).append((start, end))
            valid.append({"student_id": student.id, "roll_number": student.roll_number, "start_date": start.isoformat(), "end_date": end.isoformat(), "reason": row.get("reason", "").strip()[:160]})
        except (ValueError, KeyError) as error:
            issues.append({"row": number, "message": str(error)})
    if not valid:
        raise HTTPException(422, {"message": "No valid rebate rows", "issues": issues})
    batch = ImportBatch(id=str(uuid.uuid4()), kind="rebate", status="pending_approval", source_name=(file.filename or "rebates.csv")[:180], rows=valid, issues=issues, summary={"rows": len(rows), "valid": len(valid), "invalid": len(issues), "can_approve": not issues})
    db.add(batch)
    audit(db, "demo-site-admin", "rebate.previewed", batch.id, batch.summary)
    db.commit()
    return {"batch_id": batch.id, "status": batch.status, "summary": batch.summary, "issues": issues, "approval_required": True}


@app.get("/api/v1/admin/rebates/history")
def rebate_history(x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    batches = db.scalars(select(ImportBatch).where(ImportBatch.kind == "rebate").order_by(ImportBatch.created_at.desc()).limit(30)).all()
    return [{"batch_id": b.id, "source_name": b.source_name, "status": b.status, "created_at": b.created_at.isoformat(), "summary": b.summary, "issues": b.issues, "roll_numbers": [r.get("roll_number") for r in b.rows]} for b in batches]


@app.get("/api/v1/admin/rebates/approved")
def approved_rebate_records(start: date | None = None, end: date | None = None, x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    query = select(Rebate).order_by(Rebate.start_date.desc())
    if start:
        query = query.where(Rebate.end_date >= start)
    if end:
        query = query.where(Rebate.start_date <= end)
    result = []
    for rebate in db.scalars(query.limit(5000)).all():
        student = db.get(Student, rebate.student_id)
        result.append({"roll_number": student.roll_number if student else "", "student": student.name if student else "",
                       "course": student.course or "" if student else "", "branch": student.branch or "" if student else "",
                       "start_date": rebate.start_date.isoformat(), "end_date": rebate.end_date.isoformat(), "reason": rebate.reason or "Not specified",
                       "approved_by": rebate.approved_by, "approved_at": in_local_time(rebate.approved_at).isoformat()})
    return result


def rebate_reviewer(x_admin_key: str | None, x_finance_key: str | None, db: Session) -> StaffUser:
    if x_admin_key:
        reviewer_id = require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    else:
        reviewer_id = require_key(x_finance_key, "FINANCE_DEMO_KEY", "demo-finance-key", "Finance reviewer authentication failed", db)
    return db.get(StaffUser, reviewer_id)


@app.get("/api/v1/admin/rebates/pending")
def pending_rebates(x_admin_key: str | None = Header(default=None), x_finance_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    rebate_reviewer(x_admin_key, x_finance_key, db)
    batches = db.scalars(select(ImportBatch).where(ImportBatch.kind == "rebate", ImportBatch.status == "pending_approval").order_by(ImportBatch.created_at.asc())).all()
    student_ids = {row["student_id"] for batch in batches for row in batch.rows if row.get("student_id")}
    students = {student.id: student.name for student in db.scalars(select(Student).where(Student.id.in_(student_ids))).all()} if student_ids else {}
    return [{"batch_id": b.id, "source_name": b.source_name, "created_at": b.created_at.isoformat(),
             "summary": b.summary, "issues": b.issues,
             "rows": [{**row, "student_name": students.get(row.get("student_id"), "Unknown student")} for row in b.rows]}
            for b in batches]


@app.post("/api/v1/admin/rebates/{batch_id}/approve")
def approve_rebates(batch_id: str, x_admin_key: str | None = Header(default=None), x_finance_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    reviewer = rebate_reviewer(x_admin_key, x_finance_key, db)
    batch = db.scalar(select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update())
    if not batch or batch.kind != "rebate":
        raise HTTPException(404, "Rebate import not found")
    if batch.status != "pending_approval" or batch.issues:
        raise HTTPException(409, "Rebate batch is not eligible for approval")
    for row in batch.rows:
        overlaps = db.scalar(select(Rebate.id).where(Rebate.student_id == row["student_id"], Rebate.start_date <= date.fromisoformat(row["end_date"]), Rebate.end_date >= date.fromisoformat(row["start_date"])))
        if overlaps:
            raise HTTPException(409, "An approved rebate now overlaps this import; create a corrected import")
        student = db.get(Student, row["student_id"])
        if not student:
            raise HTTPException(409, "A student in this batch no longer exists; upload a corrected file")
        db.add(Rebate(student_id=student.id, unit_id=student.unit_id, start_date=date.fromisoformat(row["start_date"]), end_date=date.fromisoformat(row["end_date"]), batch_id=batch.id, approved_by=reviewer.email[:120], reason=row.get("reason", "")[:160]))
    batch.status, batch.approved_by, batch.confirmed_at = "approved", reviewer.email[:120], datetime.now(TZ)
    audit(db, reviewer.id, "rebate.approved", batch.id, {"rows": len(batch.rows), "reviewer_email": reviewer.email})
    db.commit()
    return {"batch_id": batch.id, "status": batch.status, "approved_rows": len(batch.rows)}


@app.post("/api/v1/admin/rebates/{batch_id}/reject")
def reject_rebates(batch_id: str, x_admin_key: str | None = Header(default=None), x_finance_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    reviewer = rebate_reviewer(x_admin_key, x_finance_key, db)
    batch = db.scalar(select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update())
    if not batch or batch.kind != "rebate":
        raise HTTPException(404, "Rebate import not found")
    if batch.status != "pending_approval":
        raise HTTPException(409, "Only pending rebate batches can be rejected")
    batch.status, batch.approved_by, batch.confirmed_at = "rejected", reviewer.email[:120], datetime.now(TZ)
    audit(db, reviewer.id, "rebate.rejected", batch.id, {"rows": len(batch.rows), "reviewer_email": reviewer.email})
    db.commit()
    return {"batch_id": batch.id, "status": batch.status}


@app.post("/api/v1/admin/billing/{month}/preview")
def billing_preview(month: str, daily_rate_paise: int = Query(default=0, ge=0, le=100000000), x_finance_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_finance_key, "FINANCE_DEMO_KEY", "demo-finance-key", "Finance reviewer authentication failed", db)
    start, end = month_bounds(month)
    unit = db.scalar(select(MessUnit).limit(1))
    students = db.scalars(select(Student).where(Student.unit_id == unit.id)).all()
    snapshot = []
    for student in students:
        allocations = db.scalars(select(Allocation).where(Allocation.student_id == student.id, Allocation.unit_id == unit.id, Allocation.start_date <= end, Allocation.end_date >= start)).all()
        allocated_days = {start + timedelta(days=i) for i in range((end - start).days + 1) if any(a.start_date <= start + timedelta(days=i) <= a.end_date for a in allocations)}
        if not allocated_days:
            continue
        rebates = db.scalars(select(Rebate).where(Rebate.student_id == student.id, Rebate.unit_id == unit.id, Rebate.start_date <= end, Rebate.end_date >= start)).all()
        rebate_days = {day for day in allocated_days if any(r.start_date <= day <= r.end_date for r in rebates)}
        billable = len(allocated_days) - len(rebate_days)
        snapshot.append({"student_id": student.id, "roll_number": student.roll_number, "name": student.name, "eligible_allocated_days": len(allocated_days), "approved_rebate_days": len(rebate_days), "billable_days": billable, "amount_paise": billable * daily_rate_paise})
    latest = db.scalar(select(func.max(BillingCycle.version)).where(BillingCycle.unit_id == unit.id, BillingCycle.cycle_month == month)) or 0
    cycle = BillingCycle(id=str(uuid.uuid4()), unit_id=unit.id, cycle_month=month, version=latest + 1, daily_rate=daily_rate_paise, snapshot=snapshot)
    db.add(cycle)
    audit(db, "demo-finance-reviewer", "billing.previewed", cycle.id, {"month": month, "version": cycle.version, "rate_paise": daily_rate_paise})
    db.commit()
    return {"cycle_id": cycle.id, "month": month, "status": cycle.status, "version": cycle.version, "daily_rate_paise": daily_rate_paise, "students": snapshot, "totals": {"eligible_allocated_days": sum(x["eligible_allocated_days"] for x in snapshot), "approved_rebate_days": sum(x["approved_rebate_days"] for x in snapshot), "billable_days": sum(x["billable_days"] for x in snapshot), "amount_paise": sum(x["amount_paise"] for x in snapshot)}}


@app.get("/api/v1/admin/billing/cycles")
def billing_cycles(x_finance_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_finance_key, "FINANCE_DEMO_KEY", "demo-finance-key", "Finance reviewer authentication failed", db)
    cycles = db.scalars(select(BillingCycle).order_by(BillingCycle.created_at.desc()).limit(30)).all()
    result = []
    for cycle in cycles:
        rows = cycle.snapshot
        result.append({"cycle_id": cycle.id, "month": cycle.cycle_month, "version": cycle.version, "status": cycle.status, "daily_rate_paise": cycle.daily_rate, "amount_paise": sum(row["amount_paise"] for row in rows), "billable_days": sum(row["billable_days"] for row in rows), "approved_by": cycle.approved_by})
    return result


@app.post("/api/v1/admin/billing/{cycle_id}/approve")
def approve_billing(cycle_id: str, approver: str = "demo-finance-reviewer", x_finance_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_finance_key, "FINANCE_DEMO_KEY", "demo-finance-key", "Finance reviewer authentication failed", db)
    cycle = db.get(BillingCycle, cycle_id)
    if not cycle:
        raise HTTPException(404, "Billing cycle not found")
    if cycle.status != "preview":
        raise HTTPException(409, "Only a preview can be approved")
    cycle.status, cycle.approved_by, cycle.approved_at = "approved", approver[:120], datetime.now(TZ)
    audit(db, approver, "billing.approved", cycle.id, {"month": cycle.cycle_month, "version": cycle.version})
    db.commit()
    return {"cycle_id": cycle.id, "status": cycle.status, "approved_by": cycle.approved_by, "approved_at": cycle.approved_at.isoformat()}


@app.get("/api/v1/admin/billing/{cycle_id}/export.csv")
def billing_export(cycle_id: str, x_finance_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    from fastapi.responses import StreamingResponse
    require_key(x_finance_key, "FINANCE_DEMO_KEY", "demo-finance-key", "Finance reviewer authentication failed", db)
    cycle = db.get(BillingCycle, cycle_id)
    if not cycle or cycle.status != "approved":
        raise HTTPException(409, "Only an approved billing snapshot can be exported")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["cycle_month", "version", "roll_number", "student_name", "eligible_allocated_days", "approved_rebate_days", "billable_days", "daily_rate_paise", "amount_paise"])
    for row in cycle.snapshot:
        writer.writerow([cycle.cycle_month, cycle.version, row["roll_number"], row["name"], row["eligible_allocated_days"], row["approved_rebate_days"], row["billable_days"], cycle.daily_rate, row["amount_paise"]])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=unifeast-{cycle.cycle_month}-v{cycle.version}.csv"})


@app.get("/api/v1/admin/audit-logs")
def audit_logs(limit: int = Query(default=100, ge=1, le=500), x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_key(x_admin_key, "ADMIN_DEMO_KEY", "demo-admin-key", "Administrator authentication failed", db)
    return [{"actor": row.actor, "action": row.action, "record_id": row.record_id, "details": row.details, "created_at": row.created_at.isoformat()} for row in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()]
