import csv
import io
import runpy
import unittest
from unittest.mock import patch
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import (
    Allocation,
    AuditLog,
    Base,
    Institution,
    MealSchedule,
    MealToken,
    MessUnit,
    Rebate,
    OTPChallenge,
    RememberedSession,
    StaffUser,
    Student,
    app,
    digest,
    get_db,
    hash_password,
)


class MealFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        with self.sessions() as db:
            institution = Institution(name="Test Institute")
            db.add(institution)
            db.flush()
            unit = MessUnit(institution_id=institution.id, name="Test Mess")
            db.add(unit)
            db.flush()
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            self.service_date = now.date()
            student = Student(institution_id=institution.id, unit_id=unit.id, name="Test Student", email="test@example.edu", phone="+910000000111", roll_number="T001", password_hash=hash_password("secret"), password_initialized=True, photo_key="synthetic.jpg")
            db.add(student)
            db.flush()
            self.student_id, self.unit_id = student.id, unit.id
            db.add(StaffUser(name="Test Admin", email="admin@unifeast.local", role="admin", password_hash=hash_password("demo-admin"), is_active=True))
            db.add(StaffUser(name="Test Finance", email="finance@unifeast.local", role="finance", password_hash=hash_password("demo-finance"), is_active=True))
            db.add(Allocation(student_id=student.id, unit_id=unit.id, start_date=self.service_date - timedelta(days=1), end_date=self.service_date + timedelta(days=1), source_batch_id="test-batch"))
            db.add(MealSchedule(unit_id=unit.id, meal_type="Breakfast", starts_at=(now - timedelta(minutes=1)).time().replace(tzinfo=None), ends_at=(now + timedelta(minutes=30)).time().replace(tzinfo=None)))
            db.commit()

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def student_headers(self, identifier="+910000000111"):
        response = self.client.post("/api/v1/auth/login", json={"identifier": identifier, "password": "secret"})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def admin_headers(self, role="admin"):
        email, password = ("admin@unifeast.local", "demo-admin") if role == "admin" else ("finance@unifeast.local", "demo-finance")
        response = self.client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"X-Admin-Key": response.json()["access_token"]}

    def test_allocated_student_gets_reference_and_slides_to_collect_once(self):
        headers = self.student_headers()
        response = self.client.post("/api/v1/student/tokens", headers=headers, json={"meal": "Breakfast"})
        self.assertEqual(response.status_code, 200, response.text)
        reference = response.json()["token"]
        self.assertTrue(reference.startswith("UF-"))
        collected = self.client.post(f"/api/v1/student/tokens/{reference}/collect", headers=headers)
        self.assertEqual(collected.status_code, 200, collected.text)
        self.assertEqual(self.client.post(f"/api/v1/student/tokens/{reference}/collect", headers=headers).status_code, 409)

    def test_daily_meal_changes_are_isolated_and_can_be_restored(self):
        admin = self.admin_headers()
        tomorrow = (self.service_date + timedelta(days=1)).isoformat()
        another_day = (self.service_date + timedelta(days=2)).isoformat()
        body = {"service_date": tomorrow, "meal": "Special Lunch", "starts_at": "12:00", "ends_at": "14:00"}
        response = self.client.post("/api/v1/admin/service-windows", headers=admin, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.post("/api/v1/admin/service-windows", headers=admin, json=body).status_code, 409)
        body["ends_at"] = "15:00"
        self.assertEqual(self.client.put("/api/v1/admin/service-windows", headers=admin, json=body).status_code, 200)
        windows = self.client.get("/api/v1/admin/service-windows", headers=admin, params={"service_date": tomorrow}).json()
        self.assertEqual(next(x for x in windows if x["meal"] == "Special Lunch")["ends_at"], "15:00")
        other = self.client.get("/api/v1/admin/service-windows", headers=admin, params={"service_date": another_day}).json()
        self.assertNotIn("Special Lunch", [x["meal"] for x in other])
        self.assertEqual(self.client.delete("/api/v1/admin/service-windows", headers=admin, params={"service_date": tomorrow, "meal": "Breakfast"}).status_code, 200)
        windows = self.client.get("/api/v1/admin/service-windows", headers=admin, params={"service_date": tomorrow}).json()
        breakfast = next(x for x in windows if x["meal"] == "Breakfast")
        self.assertTrue(breakfast["cancelled"])
        self.assertFalse(next(x for x in other if x["meal"] == "Breakfast")["cancelled"])
        restored = {"service_date": tomorrow, "meal": "Breakfast", "starts_at": breakfast["starts_at"], "ends_at": breakfast["ends_at"]}
        self.assertEqual(self.client.put("/api/v1/admin/service-windows", headers=admin, json=restored).status_code, 200)
        self.assertFalse(next(x for x in self.client.get("/api/v1/admin/service-windows", headers=admin, params={"service_date": tomorrow}).json() if x["meal"] == "Breakfast")["cancelled"])
        self.assertEqual(self.client.post("/api/v1/admin/service-windows", headers={"X-Admin-Key": self.student_headers()["Authorization"].split()[1]}, json=body).status_code, 403)

    def test_presence_records_confirmed_tokens_and_preserves_history(self):
        admin, student = self.admin_headers(), self.student_headers()
        with self.sessions() as db:
            first = db.get(Student, self.student_id)
            second = Student(institution_id=first.institution_id, unit_id=self.unit_id, name="Other Student", email="other@example.edu", phone="+910000000119", roll_number="T099", password_hash=hash_password("secret"), password_initialized=True)
            db.add(second); db.flush()
            db.add(Allocation(student_id=second.id, unit_id=self.unit_id, start_date=self.service_date, end_date=self.service_date, source_batch_id="test"))
            db.commit()
        params = {"start": self.service_date.isoformat(), "end": self.service_date.isoformat(), "meal": "Breakfast"}
        issued = self.client.post("/api/v1/student/tokens", headers=student, json={"meal": "Breakfast"})
        self.assertEqual(issued.status_code, 200, issued.text)
        token = issued.json()["token"]
        before = self.client.get("/api/v1/admin/presence", headers=admin, params=params).json()["records"]
        self.assertTrue(all(row["status"] == "Pending" and row["token_reference"] is None for row in before))
        collected = self.client.post(f"/api/v1/student/tokens/{token}/collect", headers=student)
        self.assertEqual(collected.status_code, 200, collected.text)
        with self.sessions() as db:
            db.get(Student, self.student_id).name = "Renamed Student"
            db.commit()
        response = self.client.get("/api/v1/admin/presence", headers=admin, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()["records"]
        done = next(row for row in rows if row["roll_number"] == "T001")
        self.assertEqual(done["status"], "Collected")
        self.assertEqual(done["student_name"], "Test Student")
        self.assertEqual(done["token_reference"], token)
        self.assertTrue(done["token_created_at"] and done["token_expires_at"] and done["collected_at"])
        self.assertEqual(next(row for row in rows if row["roll_number"] == "T099")["status"], "Pending")
        self.assertIn(token, self.client.get("/api/v1/admin/presence.csv", headers=admin, params=params).text)
        self.assertEqual(self.client.get("/api/v1/admin/presence", headers=admin, params={**params, "start": (self.service_date-timedelta(days=31)).isoformat()}).status_code, 422)
        self.assertEqual(self.client.delete("/api/v1/admin/service-windows", headers=admin, params={"service_date": params["start"], "meal": "Breakfast"}).status_code, 200)
        rows = self.client.get("/api/v1/admin/presence", headers=admin, params=params).json()["records"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["token_reference"], token)

    def test_removed_meal_cannot_be_collected_and_special_meal_can(self):
        admin, student = self.admin_headers(), self.student_headers()
        token = self.client.post("/api/v1/student/tokens", headers=student, json={"meal": "Breakfast"}).json()["token"]
        today = self.service_date.isoformat()
        self.assertEqual(self.client.delete("/api/v1/admin/service-windows", headers=admin, params={"service_date": today, "meal": "Breakfast"}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/v1/student/tokens/{token}/collect", headers=student).status_code, 409)
        body = {"service_date": today, "meal": "Special Lunch", "starts_at": "00:00", "ends_at": "23:59"}
        self.assertEqual(self.client.post("/api/v1/admin/service-windows", headers=admin, json=body).status_code, 200)
        special = self.client.post("/api/v1/student/tokens", headers=student, json={"meal": "Special Lunch"})
        self.assertEqual(special.status_code, 200, special.text)
        self.assertEqual(self.client.post(f"/api/v1/student/tokens/{special.json()['token']}/collect", headers=student).status_code, 200)
        response = self.client.get("/api/v1/admin/presence", headers=admin, params={"start": today, "end": today, "meal": "Special Lunch"})
        self.assertEqual(response.json()["records"][0]["status"], "Collected")

    def test_unallocated_student_is_denied_token(self):
        with self.sessions() as db:
            institution = db.query(Institution).first()
            db.add(Student(institution_id=institution.id, unit_id=self.unit_id, name="Unallocated", email="out@example.edu", phone="+910000000112", roll_number="T002", password_hash=hash_password("secret"), password_initialized=True, photo_key="synthetic.jpg"))
            db.commit()
        headers = self.student_headers("+910000000112")
        denied = self.client.post("/api/v1/student/tokens", headers=headers, json={"meal": "Breakfast"})
        self.assertEqual(denied.status_code, 403)

    def first_login_student(self):
        with self.sessions() as db:
            institute = db.query(Institution).first()
            student = Student(institution_id=institute.id, unit_id=self.unit_id, name="First Login", email="first@example.edu", phone="+910000000114", roll_number="T003", password_hash=hash_password("unknown-random"), password_initialized=False)
            db.add(student)
            db.commit()
        return student.id

    def request_email_code(self):
        with patch("app.main.send_registration_code") as send:
            requested = self.client.post("/api/v1/auth/otp/request", json={"identifier": "first@example.edu"})
        self.assertEqual(requested.status_code, 200, requested.text)
        email, code = send.call_args.args
        self.assertEqual(email, "first@example.edu")
        self.assertNotIn(code, requested.text)
        self.assertNotIn("development_code", requested.json())
        return requested.json()["challenge_id"], code

    def verify_email(self, challenge_id, code):
        result = self.client.post("/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": code})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertNotIn("access_token", result.json())
        return result.json()["registration_token"]

    def test_first_login_email_verification_then_confirmed_password(self):
        student_id = self.first_login_student()
        challenge_id, code = self.request_email_code()
        token = self.verify_email(challenge_id, code)
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)
        with self.sessions() as db:
            self.assertFalse(db.get(Student, student_id).password_initialized)
        mismatched = self.client.post("/api/v1/auth/password/setup", json={"registration_token": token, "password": "new-secure-password", "confirm_password": "different-password"})
        self.assertEqual(mismatched.status_code, 422)
        body = {"registration_token": token, "password": "new-secure-password", "confirm_password": "new-secure-password"}
        setup = self.client.post("/api/v1/auth/password/setup", json=body)
        self.assertEqual(setup.status_code, 200, setup.text)
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/password/setup", json=body).status_code, 410)
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"identifier": "first@example.edu", "password": body["password"]}).status_code, 200)
        with self.sessions() as db:
            self.assertNotEqual(db.get(Student, student_id).password_hash, body["password"])

    def test_password_setup_requires_verified_unexpired_email(self):
        self.first_login_student()
        challenge_id, code = self.request_email_code()
        body = {"registration_token": "x" * 43, "password": "new-secure-password", "confirm_password": "new-secure-password"}
        self.assertEqual(self.client.post("/api/v1/auth/password/setup", json=body).status_code, 410)
        token = self.verify_email(challenge_id, code)
        replay = self.client.post("/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": code})
        self.assertEqual(replay.status_code, 410)
        with self.sessions() as db:
            db.get(OTPChallenge, challenge_id).expires_at = datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(seconds=1)
            db.commit()
        body["registration_token"] = token
        self.assertEqual(self.client.post("/api/v1/auth/password/setup", json=body).status_code, 410)

    def test_email_attempt_limit_resend_and_existing_accounts(self):
        self.first_login_student()
        challenge_id, code = self.request_email_code()
        self.assertEqual(self.client.post("/api/v1/auth/otp/request", json={"identifier": "first@example.edu"}).status_code, 429)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.client.post("/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": wrong}).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": code}).status_code, 429)
        with self.sessions() as db:
            db.get(OTPChallenge, challenge_id).requested_at -= timedelta(minutes=2)
            db.commit()
        new_id, new_code = self.request_email_code()
        self.assertEqual(self.client.post("/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": code}).status_code, 410)
        self.verify_email(new_id, new_code)
        self.assertEqual(self.client.post("/api/v1/auth/otp/request", json={"identifier": "test@example.edu"}).status_code, 409)

    def test_unconfigured_email_does_not_issue_a_challenge(self):
        self.first_login_student()
        with patch.dict("os.environ", {"SMTP_HOST": "", "SMTP_FROM": ""}):
            result = self.client.post("/api/v1/auth/otp/request", json={"identifier": "first@example.edu"})
        self.assertEqual(result.status_code, 503)
        with self.sessions() as db:
            self.assertEqual(db.query(OTPChallenge).count(), 0)

    def test_remembered_cookie_renewal_logout_and_no_password(self):
        login = self.client.post("/api/v1/auth/login", json={"identifier": "test@example.edu", "password": "secret"})
        self.assertEqual(login.status_code, 200)
        cookie = login.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        self.assertIn("Max-Age=34560000", cookie)
        self.assertNotIn("secret", cookie)
        self.assertEqual(login.headers["cache-control"], "no-store")
        raw = self.client.cookies.get("iitj-session")
        with self.sessions() as db:
            self.assertIsNotNone(db.get(RememberedSession, digest(raw)))
            self.assertIsNone(db.get(RememberedSession, raw))
        with patch("app.main.datetime") as clock:
            clock.now.return_value = datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(days=401)
            restored = self.client.get("/api/v1/auth/session")
        self.assertEqual(restored.status_code, 200)
        self.assertIn("Max-Age=34560000", restored.headers["set-cookie"])
        self.assertEqual(self.client.cookies.get("iitj-session"), raw)
        self.client.post("/api/v1/auth/login", json={"identifier": "test@example.edu", "password": "secret"})
        raw = self.client.cookies.get("iitj-session")
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 200)
        self.client.cookies.set("iitj-session", raw)
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)

    def test_disabled_staff_cannot_restore_session_and_foreign_origin_is_blocked(self):
        self.admin_headers()
        with self.sessions() as db:
            db.query(StaffUser).filter_by(email="admin@unifeast.local").first().is_active = False
            db.commit()
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers={"Origin": "https://another.example"}).status_code, 403)

    def test_admin_uses_same_login_and_own_password(self):
        login = self.client.post("/api/v1/auth/login", json={"identifier": "admin@unifeast.local", "password": "demo-admin"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["role"], "admin")
        headers = {"X-Admin-Key": login.json()["access_token"]}
        self.assertEqual(self.client.get("/api/v1/admin/schedules", headers=headers).status_code, 200)
        student = self.client.post("/api/v1/auth/login", json={"identifier": "+910000000111", "password": "secret"}).json()
        self.assertEqual(self.client.get("/api/v1/admin/schedules", headers={"X-Admin-Key": student["access_token"]}).status_code, 403)

    def test_expired_token_is_rejected(self):
        with self.sessions() as db:
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            raw = "expired-token-value"
            db.add(MealToken(token_hash=digest(raw), student_id=self.student_id, unit_id=self.unit_id, meal_type="Breakfast", service_date=self.service_date, created_at=now - timedelta(minutes=5), expires_at=now - timedelta(minutes=2)))
            db.commit()
        response = self.client.post(f"/api/v1/student/tokens/{raw}/collect", headers=self.student_headers())
        self.assertEqual(response.status_code, 410)

    def test_allocation_import_requires_preview_and_confirmation(self):
        today = self.service_date.isoformat()
        csv_data = f"name,email,phone,roll_number,start_date,end_date\nNew Student,new@example.edu,+910000000113,T003,{today},{today}\n"
        admin = self.admin_headers()
        preview = self.client.post("/api/v1/admin/allocations/preview", headers=admin, files={"file": ("allocation.csv", csv_data, "text/csv")})
        self.assertEqual(preview.status_code, 200, preview.text)
        batch_id = preview.json()["batch_id"]
        self.assertEqual(self.client.post(f"/api/v1/admin/allocations/{batch_id}/confirm", headers=admin).status_code, 400)
        confirmed = self.client.post(f"/api/v1/admin/allocations/{batch_id}/confirm?confirm=true", headers=admin)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["students_imported"], 1)

    def test_allocation_preview_rejects_malformed_csv(self):
        today = self.service_date.isoformat()
        header = "name,email,phone,roll_number,start_date,end_date\n"
        extra = f"Student,new@example.edu,+910000000113,T003,{today},{today},extra\n"
        admin = self.admin_headers()
        for row in (extra, '"unclosed', 'X' * 131073):
            with self.subTest(row_size=len(row)):
                response = self.client.post("/api/v1/admin/allocations/preview", headers=admin, files={"file": ("allocation.csv", header + row, "text/csv")})
                self.assertEqual(response.status_code, 422, response.text)

    def test_allocation_confirmation_rechecks_overlaps_after_preview(self):
        today = self.service_date.isoformat()
        csv_data = f"name,email,phone,roll_number,start_date,end_date\nNew Student,new@example.edu,+910000000113,T003,{today},{today}\n"
        admin = self.admin_headers()
        batch_ids = []
        for _ in range(2):
            response = self.client.post("/api/v1/admin/allocations/preview", headers=admin, files={"file": ("allocation.csv", csv_data, "text/csv")})
            self.assertEqual(response.status_code, 200, response.text)
            batch_ids.append(response.json()["batch_id"])
        for batch_id, expected in zip(batch_ids, (200, 409)):
            response = self.client.post(f"/api/v1/admin/allocations/{batch_id}/confirm?confirm=true", headers=admin)
            self.assertEqual(response.status_code, expected, response.text)

    def test_rebate_approval_reduces_billing_days_and_exports_approved_snapshot(self):
        start = self.service_date.isoformat()
        csv_data = f"roll_number,start_date,end_date\nT001,{start},{start}\n"
        preview = self.client.post("/api/v1/admin/rebates/preview", headers=self.admin_headers(), files={"file": ("rebates.csv", csv_data, "text/csv")})
        self.assertEqual(preview.status_code, 200, preview.text)
        batch_id = preview.json()["batch_id"]
        finance = self.admin_headers("finance")
        pending = self.client.get("/api/v1/admin/rebates/pending", headers={"X-Finance-Key": finance["X-Admin-Key"]})
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertEqual(pending.json()[0]["batch_id"], batch_id)
        approved = self.client.post(f"/api/v1/admin/rebates/{batch_id}/approve", headers={"X-Finance-Key": finance["X-Admin-Key"]})
        self.assertEqual(approved.status_code, 200, approved.text)
        month = self.service_date.strftime("%Y-%m")
        billing = self.client.post(f"/api/v1/admin/billing/{month}/preview?daily_rate_paise=500", headers={"X-Finance-Key": finance["X-Admin-Key"]})
        self.assertEqual(billing.status_code, 200, billing.text)
        row = next(x for x in billing.json()["students"] if x["roll_number"] == "T001")
        self.assertEqual(row["approved_rebate_days"], 1)
        self.assertEqual(row["amount_paise"], row["billable_days"] * 500)
        cycle_id = billing.json()["cycle_id"]
        self.assertEqual(self.client.get(f"/api/v1/admin/billing/{cycle_id}/export.csv", headers={"X-Finance-Key": finance["X-Admin-Key"]}).status_code, 409)
        finalized = self.client.post(f"/api/v1/admin/billing/{cycle_id}/approve", headers={"X-Finance-Key": finance["X-Admin-Key"]})
        self.assertEqual(finalized.status_code, 200)
        export = self.client.get(f"/api/v1/admin/billing/{cycle_id}/export.csv", headers={"X-Finance-Key": finance["X-Admin-Key"]})
        self.assertEqual(export.status_code, 200)
        self.assertIn("approved_rebate_days", export.text)

    def test_admin_can_review_approve_and_reject_rebate_batches(self):
        admin = self.admin_headers()
        start = self.service_date.isoformat()
        csv_data = f"roll_number,start_date,end_date,reason\nT001,{start},{start},Home visit\n"
        preview = self.client.post("/api/v1/admin/rebates/preview", headers=admin, files={"file": ("requests.csv", csv_data, "text/csv")})
        self.assertEqual(preview.status_code, 200, preview.text)
        batch_id = preview.json()["batch_id"]

        pending = self.client.get("/api/v1/admin/rebates/pending", headers=admin)
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertEqual(pending.json()[0]["rows"][0]["student_name"], "Test Student")
        self.assertEqual(pending.json()[0]["rows"][0]["reason"], "Home visit")
        student_token = self.client.post("/api/v1/auth/login", json={"identifier": "T001", "password": "secret"}).json()["access_token"]
        self.assertEqual(self.client.get("/api/v1/admin/rebates/pending", headers={"X-Admin-Key": student_token}).status_code, 403)
        self.assertEqual(self.client.post(f"/api/v1/admin/rebates/{batch_id}/approve", headers={"X-Admin-Key": student_token}).status_code, 403)

        approved = self.client.post(f"/api/v1/admin/rebates/{batch_id}/approve?approver=someone-else", headers=admin)
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["approved_rows"], 1)
        self.assertEqual(self.client.get("/api/v1/admin/rebates/pending", headers=admin).json(), [])
        self.assertEqual(self.client.post(f"/api/v1/admin/rebates/{batch_id}/reject", headers=admin).status_code, 409)
        with self.sessions() as db:
            rebate = db.query(Rebate).filter_by(batch_id=batch_id).one()
            audit = db.query(AuditLog).filter_by(record_id=batch_id, action="rebate.approved").one()
            reviewer = db.query(StaffUser).filter_by(email="admin@unifeast.local").one()
            self.assertEqual(rebate.approved_by, reviewer.email)
            self.assertEqual(audit.actor, reviewer.id)

        later = (self.service_date + timedelta(days=3)).isoformat()
        rejected_csv = f"roll_number,start_date,end_date\nT001,{later},{later}\n"
        second = self.client.post("/api/v1/admin/rebates/preview", headers=admin, files={"file": ("reject.csv", rejected_csv, "text/csv")}).json()["batch_id"]
        rejected = self.client.post(f"/api/v1/admin/rebates/{second}/reject", headers=admin)
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "rejected")
        with self.sessions() as db:
            self.assertEqual(db.query(Rebate).filter_by(batch_id=second).count(), 0)
        self.assertEqual(self.client.post(f"/api/v1/admin/rebates/{second}/approve", headers=admin).status_code, 409)

    def test_invalid_rebate_batch_can_be_reviewed_and_rejected_but_not_approved(self):
        admin = self.admin_headers()
        day = self.service_date.isoformat()
        csv_data = f"roll_number,start_date,end_date\nT001,{day},{day}\nUNKNOWN,{day},{day}\n"
        preview = self.client.post("/api/v1/admin/rebates/preview", headers=admin, files={"file": ("invalid.csv", csv_data, "text/csv")})
        self.assertEqual(preview.status_code, 200, preview.text)
        batch_id = preview.json()["batch_id"]
        pending = self.client.get("/api/v1/admin/rebates/pending", headers=admin).json()[0]
        self.assertEqual(pending["summary"]["invalid"], 1)
        self.assertIn("not registered", pending["issues"][0]["message"])
        self.assertEqual(self.client.post(f"/api/v1/admin/rebates/{batch_id}/approve", headers=admin).status_code, 409)
        self.assertEqual(self.client.post(f"/api/v1/admin/rebates/{batch_id}/reject", headers=admin).status_code, 200)

    def test_sample_files_support_mess_capacity_students_and_rebates(self):
        sample_rows = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "generate_sample_data.py"))["sample_rows"]
        student_rows, rebate_rows = sample_rows(self.service_date)

        def as_csv(rows):
            result = io.StringIO(newline="")
            csv.writer(result).writerows(rows)
            return result.getvalue().encode("utf-8")

        admin = self.admin_headers()
        preview = self.client.post("/api/v1/admin/allocations/preview", headers=admin, files={"file": ("students.csv", as_csv(student_rows), "text/csv")})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["summary"]["valid"], 40)
        self.assertEqual(preview.json()["summary"]["invalid"], 0)
        batch = preview.json()["batch_id"]
        confirmed = self.client.post(f"/api/v1/admin/allocations/{batch}/confirm?confirm=true", headers=admin)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["students_imported"], 40)

        capacity = self.client.put(f"/api/v1/admin/units/{self.unit_id}/capacity?capacity=50", headers=admin)
        self.assertEqual(capacity.status_code, 200, capacity.text)
        unit = self.client.get("/api/v1/admin/units", headers=admin).json()[0]
        self.assertEqual(unit["students"], 41)
        self.assertEqual(unit["occupancy_percent"], 82)

        rebate = self.client.post("/api/v1/admin/rebates/preview", headers=admin, files={"file": ("rebates.csv", as_csv(rebate_rows), "text/csv")})
        self.assertEqual(rebate.status_code, 200, rebate.text)
        self.assertEqual(rebate.json()["summary"]["valid"], 10)
        finance = self.admin_headers("finance")
        approved = self.client.post(f"/api/v1/admin/rebates/{rebate.json()['batch_id']}/approve", headers={"X-Finance-Key": finance["X-Admin-Key"]})
        self.assertEqual(approved.status_code, 200, approved.text)

        start = (self.service_date - timedelta(days=14)).isoformat()
        end = (self.service_date + timedelta(days=14)).isoformat()
        analytics = self.client.get(f"/api/v1/admin/analytics?start={start}&end={end}", headers=admin)
        self.assertEqual(analytics.status_code, 200, analytics.text)
        self.assertEqual(analytics.json()["students_on_rebate"], 10)
        self.assertEqual(analytics.json()["rebate_requests"], 10)
        self.assertEqual(set(analytics.json()["demographics"]), {"gender", "course", "branch"})


if __name__ == "__main__":
    unittest.main()
