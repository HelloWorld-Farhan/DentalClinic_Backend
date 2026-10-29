import uuid
import sys
from pathlib import Path

# Ensure prescription package is importable
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from prescription.main import app
from prescription.database import SessionLocal
from prescription.models import User, UserSession

client = TestClient(app)

def test_revoked_session_otp_rechallenge():
    email = f"test.rechallenge.{uuid.uuid4().hex[:6]}@smileclinic.com"
    password = "StrongPassword2026#"
    device_id = f"dev-test-{uuid.uuid4().hex[:8]}"

    print(f"=== Starting Session Revocation OTP Rechallenge Test for {email} ===")

    # 1. Signup & verify account
    signup_res = client.post("/api/v1/auth/signup", json={
        "full_name": "Dr. Test Rechallenge",
        "email": email,
        "password": password,
        "phone": "+1 555-9988",
        "role": "USER"
    })
    assert signup_res.status_code == 200
    otp = signup_res.json()["dev_otp"]
    v_res = client.post("/api/v1/auth/verify-otp", json={"email": email, "otp_code": otp})
    assert v_res.status_code == 200
    print("[PASS] Signup and initial account verification completed.")

    # 2. First login on new device with remember_device=True -> Requires OTP!
    login_1 = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
        "remember_device": True,
        "device_id": device_id
    })
    assert login_1.status_code == 200
    assert login_1.json()["status"] == "otp_required", f"Expected otp_required, got: {login_1.json()}"
    first_otp = login_1.json()["dev_otp"]
    print(f"[PASS] First login on new device required OTP: {first_otp}")

    # 3. Verify OTP with remember_device=True -> Successfully authenticated & remembered
    otp_res = client.post("/api/v1/auth/verify-login-otp", json={
        "email": email,
        "otp_code": first_otp,
        "remember_device": True,
        "device_id": device_id
    })
    assert otp_res.status_code == 200
    assert otp_res.json()["status"] == "success"
    print("[PASS] verify-login-otp succeeded with remember_device=True.")

    # Also record active session in DB as frontend does
    rec_res = client.post("/api/v1/auth/record-session", json={
        "email": email,
        "device_id": device_id,
        "device_name": "Samsung Galaxy S24 Ultra",
        "browser_os": "Chrome Mobile • Android 14",
        "status": "Success"
    })
    assert rec_res.status_code == 200
    print("[PASS] Active session recorded in database.")

    # 4. Subsequent login on remembered device -> Direct access, NO OTP required!
    login_2 = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
        "remember_device": True,
        "device_id": device_id
    })
    assert login_2.status_code == 200
    assert login_2.json()["status"] == "success"
    assert "token" in login_2.json()
    print("[PASS] Subsequent login succeeded directly without OTP challenge.")

    # 5. Revoke session remotely from Settings
    revoke_res = client.post("/api/v1/auth/revoke-session", json={
        "email": email,
        "device_id": device_id,
        "device_name": "Samsung Galaxy S24 Ultra"
    })
    assert revoke_res.status_code == 200
    assert revoke_res.json()["status"] == "success"
    print(f"[PASS] Session revoked from settings: {revoke_res.json()['message']}")

    # 6. Check heartbeat endpoint confirms revocation
    heartbeat_res = client.get(f"/api/v1/auth/session-status?email={email}&device_id={device_id}")
    assert heartbeat_res.status_code == 200
    assert heartbeat_res.json()["revoked"] is True
    print("[PASS] Heartbeat session status accurately reports session as revoked.")

    # 7. Next login attempt from that revoked device -> MUST REQUIRE OTP RE-CHALLENGE!
    login_3 = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
        "remember_device": True,
        "device_id": device_id
    })
    assert login_3.status_code == 200
    assert login_3.json()["status"] == "otp_required", f"Expected otp_required after revocation, got: {login_3.json()}"
    rechallenge_otp = login_3.json()["dev_otp"]
    print(f"[PASS] Revoked workstation login strictly forced OTP re-challenge! OTP: {rechallenge_otp}")

    # 8. Submit OTP verification for the revoked device
    otp_rechallenge_res = client.post("/api/v1/auth/verify-login-otp", json={
        "email": email,
        "otp_code": rechallenge_otp,
        "remember_device": True,
        "device_id": device_id
    })
    assert otp_rechallenge_res.status_code == 200
    assert otp_rechallenge_res.json()["status"] == "success"
    print("[PASS] OTP re-challenge verified and re-activated the device.")

    # 9. Next login attempt -> Succeeds directly again without OTP!
    login_4 = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
        "remember_device": True,
        "device_id": device_id
    })
    assert login_4.status_code == 200
    assert login_4.json()["status"] == "success"
    assert "token" in login_4.json()
    print("[PASS] Workstation re-authorized; subsequent logins proceed without OTP.")

    print("\n=== ALL 9 SECURITY VERIFICATION STEPS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_revoked_session_otp_rechallenge()
