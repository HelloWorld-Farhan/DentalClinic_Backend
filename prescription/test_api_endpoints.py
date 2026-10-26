import uuid
import os
import sys
from pathlib import Path

# Ensure prescription package is importable
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from prescription.main import app

client = TestClient(app)

def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    print("[PASS] /health endpoint healthy")

def test_signup_verify_and_login_flow():
    unique_email = f"dr.smith.{uuid.uuid4().hex[:6]}@smileclinic.com"
    password = "StrongPassword2026#"

    print(f"Testing Prescription Signup for: {unique_email}")
    signup_res = client.post("/api/v1/auth/signup", json={
        "full_name": "Dr. Sarah Smith, DDS",
        "email": unique_email,
        "password": password,
        "phone": "+1 555-0192",
        "role": "DOCTOR",
        "license_number": "DDS-884920",
        "clinic_id": "CLINIC-MAIN"
    })
    print("Signup Status:", signup_res.status_code, signup_res.json())
    assert signup_res.status_code == 200, "Signup endpoint failed"
    data = signup_res.json()
    assert data["status"] == "success"
    otp_code = data.get("dev_otp")
    assert otp_code and len(otp_code) == 6, "OTP code not returned in dev mode"

    print("Testing Prescription Verify OTP...")
    verify_res = client.post("/api/v1/auth/verify-otp", json={
        "email": unique_email,
        "otp_code": otp_code
    })
    print("Verify Status:", verify_res.status_code, verify_res.json())
    assert verify_res.status_code == 200, "Verify OTP failed"
    vdata = verify_res.json()
    assert vdata["token"] is not None, "Missing token on verification"
    assert vdata["user"]["email"] == unique_email

    print("Testing Prescription Login...")
    login_res = client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": password
    })
    print("Login Status:", login_res.status_code, login_res.json())
    assert login_res.status_code == 200, "Login failed"
    ldata = login_res.json()
    assert ldata["token"] is not None
    assert ldata["user"]["fullName"] == "Dr. Sarah Smith, DDS"

    print("--- ALL PRESCRIPTION API TESTS PASSED SUCCESSFULLY ---")

if __name__ == "__main__":
    test_health_check()
    test_signup_verify_and_login_flow()
