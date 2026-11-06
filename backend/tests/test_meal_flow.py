import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import (
    Allocation,
    Base,
    Institution,
    MealSchedule,
    MealToken,
    MessUnit,
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

    def test_unallocated_student_is_denied_token(self):
        with self.sessions() as db:
            institution = db.query(Institution).first()
            db.add(Student(institution_id=institution.id, unit_id=self.unit_id, name="Unallocated", email="out@example.edu", phone="+910000000112", roll_number="T002", password_hash=hash_password("secret"), password_initialized=True, photo_key="synthetic.jpg"))
            db.commit()
        headers = self.student_headers("+910000000112")
        denied = self.client.post("/api/v1/student/tokens", headers=headers, json={"meal": "Breakfast"})
        self.assertEqual(denied.status_code, 403)

    def test_first_login_otp_sets_student_password(self):
        with self.sessions() as db:
            institute = db.query(Institution).first()
            db.add(Student(institution_id=institute.id, unit_id=self.unit_id, name="First Login", email="first@example.edu", phone="+910000000114", roll_number="T003", password_hash=hash_password("unknown-random"), password_initialized=False))
            db.commit()
        requested = self.client.post("/api/v1/auth/otp/request", json={"identifier": "T003"})
        self.assertEqual(requested.status_code, 200)
        challenge = requested.json()
        first_try = self.client.post("/api/v1/auth/otp/verify", json={"challenge_id": challenge["challenge_id"], "code": challenge["development_code"]})
        self.assertEqual(first_try.status_code, 422)
        setup = self.client.post("/api/v1/auth/otp/verify", json={"challenge_id": challenge["challenge_id"], "code": challenge["development_code"], "new_password": "new-secure-password"})
        self.assertEqual(setup.status_code, 200, setup.text)
        signed_in = self.client.post("/api/v1/auth/login", json={"identifier": "T003", "password": "new-secure-password"})
        self.assertEqual(signed_in.status_code, 200)
        self.assertEqual(signed_in.json()["role"], "student")

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


if __name__ == "__main__":
    unittest.main()

