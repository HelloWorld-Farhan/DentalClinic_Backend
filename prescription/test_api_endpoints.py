import uuid
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure prescription package is importable
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from prescription.main import app
from prescription.database import SessionLocal
from prescription.models import User, AuthOtp

client = TestClient(app)

def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    print("[PASS] /health endpoint healthy")

def test_signup_verify_and_login_flow():
    unique_email = f"dr.smith.{uuid.uuid4().hex[:6]}@smileclinic.com"
    password = "StrongPassword2026#"

    print(f"\n1. Testing Prescription Signup for: {unique_email}")
    signup_res = client.post("/api/v1/auth/signup", json={
        "full_name": "Dr. Sarah Smith, DDS",
        "email": unique_email,
        "password": password,
        "phone": "+1 555-0192",
        "role": "DOCTOR",
        "license_number": "DDS-884920",
        "clinic_id": "CLINIC-MAIN"
    })
    assert signup_res.status_code == 200
    data = signup_res.json()
    assert data["status"] == "success"
    otp_code = data.get("dev_otp")
    assert otp_code and len(otp_code) == 6

    print("2. Testing Prescription Verify OTP...")
    verify_res = client.post("/api/v1/auth/verify-otp", json={
        "email": unique_email,
        "otp_code": otp_code
    })
    assert verify_res.status_code == 200
    vdata = verify_res.json()
    assert vdata["token"] is not None

    print("3. Testing Prescription Successful Login...")
    login_res = client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": password
    })
    assert login_res.status_code == 200
    print("[PASS] Happy path signup -> OTP -> login passed.")
    return unique_email, password

def test_brute_force_lockout_and_password_reset(email: str, original_password: str):
    print(f"\n--- TESTING BRUTE FORCE & LOCKOUT FLOW FOR: {email} ---")
    
    # Attempt 1: Wrong password
    res1 = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword1#"})
    print("Attempt 1 Status:", res1.status_code, res1.json())
    assert res1.status_code == 401
    assert "2 attempts remaining" in res1.json()["detail"]

    # Attempt 2: Rapid-fire attempt (within 60s) -> 429 Too Many Requests
    res2_rapid = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword2#"})
    print("Attempt 2 (Rapid) Status:", res2_rapid.status_code, res2_rapid.json())
    assert res2_rapid.status_code == 429
    assert "Security rate limit in effect" in res2_rapid.json()["detail"]

    # Fast-forward simulated timestamp for test purposes
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    assert user is not None
    user.last_failed_attempt = datetime.now(timezone.utc) - timedelta(seconds=65)
    db.commit()

    # Attempt 2 (after rate limit cooldown): Wrong password -> 1 attempt remaining
    res2 = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword2#"})
    print("Attempt 2 Status:", res2.status_code, res2.json())
    assert res2.status_code == 401
    assert "1 attempt remaining" in res2.json()["detail"]

    # Fast-forward cooldown for 3rd attempt
    user.last_failed_attempt = datetime.now(timezone.utc) - timedelta(seconds=65)
    db.commit()

    # Attempt 3: Wrong password -> Account locked + auto OTP dispatched!
    res3 = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword3#"})
    print("Attempt 3 Status (Lockout):", res3.status_code, res3.json())
    assert res3.status_code == 403
    assert "Account locked due to 3 failed login attempts" in res3.json()["detail"]

    # Verify an OTP was saved in auth_otps
    otp_record = db.query(AuthOtp).filter(AuthOtp.email == email).order_by(AuthOtp.created_at.desc()).first()
    assert otp_record is not None
    reset_otp = otp_record.otp_code
    print(f"[PASS] Lockout triggered. Reset OTP generated: {reset_otp}")

    # Subsequent attempt even with correct password is now blocked because account is locked!
    blocked_res = client.post("/api/v1/auth/login", json={"email": email, "password": original_password})
    assert blocked_res.status_code == 403
    print("[PASS] Account properly locked against all login attempts.")

    # Reset Password with OTP
    new_password = "BrandNewSecurePassword2026#"
    reset_res = client.post("/api/v1/auth/reset-password", json={
        "email": email,
        "otp_code": reset_otp,
        "new_password": new_password
    })
    print("Reset Password Status:", reset_res.status_code, reset_res.json())
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "success"

    # Login with new password now succeeds and resets all locks
    new_login_res = client.post("/api/v1/auth/login", json={"email": email, "password": new_password})
    assert new_login_res.status_code == 200
    if new_login_res.json().get("status") == "otp_required":
        otp = new_login_res.json().get("dev_otp")
        v_res = client.post("/api/v1/auth/verify-login-otp", json={"email": email, "otp_code": otp})
        assert v_res.status_code == 200
        assert v_res.json()["token"] is not None
    else:
        assert new_login_res.json()["token"] is not None
    print("[PASS] Login with new password succeeded!")

    db.close()
    print("--- ALL BRUTE FORCE & LOCKOUT TESTS PASSED ---")

def test_remember_device_flows(email: str, password: str):
    print(f"\n--- TESTING REMEMBER DEVICE FLOWS FOR: {email} ---")
    
    # 0. Test toggle-2fa endpoint
    print("0. Testing toggle-2fa endpoint to disable 2FA for direct login testing...")
    res_toggle_off = client.post("/api/v1/auth/toggle-2fa", json={"email": email, "enabled": False})
    assert res_toggle_off.status_code == 200
    assert res_toggle_off.json()["user"]["twoFactorEnabled"] is False
    print("[PASS] 2FA disabled successfully.")

    # 1. Login with remember_device=True and 2FA disabled -> Direct login, no OTP required
    print("1. Testing login with 2FA disabled & remember_device=True...")
    res_remembered = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
        "remember_device": True,
        "device_id": "test_trusted_device_01"
    })
    print("Remembered Device Login Status:", res_remembered.status_code, res_remembered.json())
    assert res_remembered.status_code == 200
    assert res_remembered.json()["status"] == "success"
    assert res_remembered.json()["token"] is not None
    print("[PASS] Remember Device=True allows direct access without OTP.")

    # 2. Toggle 2FA back ON -> Enforces OTP requirement even with remember_device=True
    print("2. Testing toggle-2fa endpoint to enable 2FA...")
    res_toggle_on = client.post("/api/v1/auth/toggle-2fa", json={"email": email, "enabled": True})
    assert res_toggle_on.status_code == 200
    assert res_toggle_on.json()["user"]["twoFactorEnabled"] is True
    print("[PASS] 2FA enabled successfully.")

    # 3. Login with 2FA enabled -> Requires 2FA OTP verification
    print("3. Testing login with 2FA enabled...")
    res_2fa_login = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
        "remember_device": True,
        "device_id": "test_trusted_device_01"
    })
    print("2FA Required Login Status:", res_2fa_login.status_code, res_2fa_login.json())
    assert res_2fa_login.status_code == 200
    assert res_2fa_login.json()["status"] == "otp_required"
    login_otp = res_2fa_login.json().get("dev_otp")
    assert login_otp and len(login_otp) == 6
    print(f"[PASS] 2FA enabled triggers OTP requirement. OTP: {login_otp}")

    # 4. Complete login with verify-login-otp
    print("4. Testing verify-login-otp endpoint...")
    verify_login_res = client.post("/api/v1/auth/verify-login-otp", json={
        "email": email,
        "otp_code": login_otp,
        "remember_device": True
    })
    print("Verify Login OTP Status:", verify_login_res.status_code, verify_login_res.json())
    assert verify_login_res.status_code == 200
    assert verify_login_res.json()["status"] == "success"
    assert verify_login_res.json()["token"] is not None
    print("[PASS] verify-login-otp successfully returns session JWT!")

if __name__ == "__main__":
    test_health_check()
    email, password = test_signup_verify_and_login_flow()
    test_remember_device_flows(email, password)
    test_brute_force_lockout_and_password_reset(email, password)
