import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import bcrypt
import jwt
import requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, AuthOtp
from ..schemas import (
    SignupRequest,
    VerifyOtpRequest,
    ResendOtpRequest,
    LoginRequest,
    VerifyLoginOtpRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyResetOtpRequest,
    VerifyPasswordRequest,
    ChangePasswordRequest,
    Toggle2FaRequest,
    GoogleAuthRequest,
    AuthResponse
)

router = APIRouter(prefix="/api/v1/auth", tags=["Prescription Authentication"])

JWT_SECRET = os.getenv("JWT_SECRET", "smileclinic_jwt_secret_dev_key_2026_super_secure_clinical")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7
GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL")
PORTAL_LOGIN_URL = os.getenv("PORTAL_LOGIN_URL", os.getenv("FRONTEND_URL", "http://localhost:5173/login"))

def get_template_path(template_name: str) -> Optional[Path]:
    """Finds templates/ in project hierarchy dynamically without hardcoded paths."""
    current = Path(__file__).resolve()
    for parent in [current.parent, current.parents[1], current.parents[2], current.parents[3]]:
        candidate = parent / "templates" / template_name
        if candidate.exists():
            return candidate
    return None

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_jwt_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "name": user.full_name,
        "license_number": user.license_number,
        "clinic_id": user.clinic_id,
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def generate_numeric_otp(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))

def send_template_email(to_email: str, subject: str, template_name: str, context: dict) -> bool:
    """Renders HTML template from templates/ and sends via Google Apps Script Mail Gateway."""
    template_file = get_template_path(template_name)
    if template_file and template_file.exists():
        with open(template_file, "r", encoding="utf-8") as f:
            html_content = f.read()
        for k, v in context.items():
            html_content = html_content.replace(f"{{{{ {k} }}}}", str(v))
            html_content = html_content.replace(f"{{{{{k}}}}}", str(v))
    else:
        html_content = f"<h2>Smile Clinic</h2><p>{subject}</p>"

    if not GOOGLE_APPS_SCRIPT_URL:
        print(f"[AUTH_EMAIL_DEV] GOOGLE_APPS_SCRIPT_URL unset; email to {to_email} captured in local dev mode.")
        return False

    try:
        res = requests.post(
            GOOGLE_APPS_SCRIPT_URL,
            json={
                "to": to_email,
                "subject": subject,
                "html": html_content
            },
            timeout=10
        )
        if res.status_code == 200:
            print(f"[AUTH_EMAIL_SUCCESS] Dispatched '{template_name}' to {to_email} via Google Apps Script.")
            return True
        else:
            print(f"[AUTH_EMAIL_ERROR] Apps Script returned status {res.status_code}: {res.text}")
            return False
    except Exception as e:
        print(f"[AUTH_EMAIL_EXCEPTION] Email delivery skipped: {e}")
        return False


@router.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    existing_user = db.query(User).filter(User.email == email_clean).first()

    if existing_user and existing_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A clinician account with this email address already exists. Please sign in."
        )

    hashed_pwd = hash_password(payload.password)

    if existing_user:
        existing_user.full_name = payload.full_name.strip()
        existing_user.hashed_password = hashed_pwd
        existing_user.phone = payload.phone
        existing_user.role = payload.role or "PHARMACIST"
        existing_user.license_number = payload.license_number
        existing_user.clinic_id = payload.clinic_id or "CLINIC-MAIN"
        user = existing_user
    else:
        user = User(
            email=email_clean,
            full_name=payload.full_name.strip(),
            hashed_password=hashed_pwd,
            phone=payload.phone,
            role=payload.role or "PHARMACIST",
            license_number=payload.license_number,
            clinic_id=payload.clinic_id or "CLINIC-MAIN",
            is_verified=False
        )
        db.add(user)

    otp_code = generate_numeric_otp(6)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()
    otp_record = AuthOtp(
        email=email_clean,
        otp_code=otp_code,
        expires_at=expires_at
    )
    db.add(otp_record)
    db.commit()

    send_template_email(
        to_email=email_clean,
        subject=f"Smile Clinic — Your Verification Code: {otp_code}",
        template_name="otp_verification.html",
        context={
            "clinician_name": payload.full_name.strip(),
            "otp_code": otp_code,
            "expires_in_minutes": 10
        }
    )

    return AuthResponse(
        status="success",
        message="Registration initiated. A 6-digit verification code has been dispatched to your email.",
        dev_otp=otp_code
    )


@router.post("/verify-otp", response_model=AuthResponse)
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    otp_code_clean = payload.otp_code.strip()

    otp_record = (
        db.query(AuthOtp)
        .filter(AuthOtp.email == email_clean)
        .order_by(AuthOtp.created_at.desc())
        .first()
    )

    if not otp_record or otp_record.otp_code != otp_code_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 6-digit verification code. Please check and try again."
        )

    now_utc = datetime.now(timezone.utc)
    record_expires = otp_record.expires_at
    if record_expires.tzinfo is None:
        record_expires = record_expires.replace(tzinfo=timezone.utc)

    if now_utc > record_expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The verification code has expired. Please request a new code."
        )

    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinician record not found. Please register again."
        )

    user.is_verified = True
    db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()
    db.commit()
    db.refresh(user)

    token = create_jwt_token(user)

    send_template_email(
        to_email=email_clean,
        subject="Welcome to Smile Clinic — Clinical Account Activated",
        template_name="welcome_clinician.html",
        context={
            "clinician_name": user.full_name,
            "clinician_email": user.email,
            "portal_login_url": PORTAL_LOGIN_URL
        }
    )

    return AuthResponse(
        status="success",
        message="Account verified successfully! Welcome to Smile Clinic.",
        token=token,
        user={
            "id": user.id,
            "email": user.email,
            "fullName": user.full_name,
            "role": user.role,
            "licenseNumber": user.license_number or user.id,
            "clinicId": user.clinic_id,
            "twoFactorEnabled": getattr(user, 'two_factor_enabled', False)
        }
    )


@router.post("/resend-otp", response_model=AuthResponse)
def resend_otp(payload: ResendOtpRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No clinician account found for this email address."
        )

    otp_code = generate_numeric_otp(6)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()
    otp_record = AuthOtp(
        email=email_clean,
        otp_code=otp_code,
        expires_at=expires_at
    )
    db.add(otp_record)
    db.commit()

    send_template_email(
        to_email=email_clean,
        subject=f"Smile Clinic — Your Verification Code: {otp_code}",
        template_name="otp_verification.html",
        context={
            "clinician_name": user.full_name,
            "otp_code": otp_code,
            "expires_in_minutes": 10
        }
    )

    return AuthResponse(
        status="success",
        message="A new 6-digit verification code has been dispatched to your email.",
        dev_otp=otp_code
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Please verify your credentials."
        )

    now = datetime.now(timezone.utc)

    # 1. Check if account is locked due to 3+ previous failed attempts
    if (user.failed_login_attempts or 0) >= 3 or (user.locked_until and user.locked_until > now):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account locked due to 3 failed login attempts. A verification code has been dispatched to your email to verify your identity and reset your password."
        )

    # 2. Enforce 1-minute brute force rate-limiting cooldown if prior failed attempt
    if user.last_failed_attempt and (user.failed_login_attempts or 0) > 0:
        last_time = user.last_failed_attempt.replace(tzinfo=timezone.utc) if user.last_failed_attempt.tzinfo is None else user.last_failed_attempt
        elapsed = (now - last_time).total_seconds()
        if elapsed < 60:
            seconds_left = max(1, int(60 - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Security rate limit in effect. Please wait {seconds_left} second{'s' if seconds_left > 1 else ''} before attempting again."
            )

    # 3. Check password
    if not verify_password(payload.password, user.hashed_password):
        user.last_failed_attempt = now
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

        if user.failed_login_attempts < 3:
            remaining = 3 - user.failed_login_attempts
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Incorrect password. {remaining} attempt{'s' if remaining > 1 else ''} remaining."
            )
        else:
            # 3rd failure: lock account and auto-dispatch OTP via password_reset_otp.html
            user.failed_login_attempts = 3
            user.locked_until = now + timedelta(days=365)
            otp_code = generate_numeric_otp(6)
            expires_at = now + timedelta(minutes=10)
            db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()
            db.add(AuthOtp(email=email_clean, otp_code=otp_code, expires_at=expires_at))
            db.commit()

            send_template_email(
                to_email=email_clean,
                subject=f"Smile Clinic Security Alert — Account Locked: Reset Code {otp_code}",
                template_name="password_reset_otp.html",
                context={
                    "clinician_name": user.full_name,
                    "clinician_email": user.email,
                    "reset_code": otp_code,
                    "expires_in_minutes": 10
                }
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account locked due to 3 failed login attempts. A verification code has been dispatched to your email to verify your identity and reset your password."
            )

    # 4. Handle unverified clinician account
    if not user.is_verified:
        otp_code = generate_numeric_otp(6)
        expires_at = now + timedelta(minutes=10)
        db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()
        db.add(AuthOtp(email=email_clean, otp_code=otp_code, expires_at=expires_at))
        db.commit()

        send_template_email(
            to_email=email_clean,
            subject=f"Smile Clinic — Your Verification Code: {otp_code}",
            template_name="otp_verification.html",
            context={
                "clinician_name": user.full_name,
                "otp_code": otp_code,
                "expires_in_minutes": 10
            }
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not verified yet. A verification code has been sent to your email."
        )

    # 5. Check "Two-Factor Authentication" setting
    two_fa_active = bool(getattr(user, 'two_factor_enabled', False))
    if two_fa_active:
        otp_code = generate_numeric_otp(6)
        expires_at = now + timedelta(minutes=10)
        db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()
        db.add(AuthOtp(email=email_clean, otp_code=otp_code, expires_at=expires_at))
        db.commit()

        send_template_email(
            to_email=email_clean,
            subject=f"Smile Clinic — Sign-In Verification Code: {otp_code}",
            template_name="otp_verification.html",
            context={
                "clinician_name": user.full_name,
                "otp_code": otp_code,
                "expires_in_minutes": 10
            }
        )

        return AuthResponse(
            status="otp_required",
            message="Two-factor verification required. A 6-digit sign-in code has been dispatched to your email.",
            dev_otp=otp_code
        )

    # If remember_device is True, direct login without OTP friction
    if payload.device_id:
        user.remembered_device_id = payload.device_id

    user.failed_login_attempts = 0
    user.last_failed_attempt = None
    user.locked_until = None
    db.commit()

    token = create_jwt_token(user)

    return AuthResponse(
        status="success",
        message="Login successful.",
        token=token,
        user={
            "id": user.id,
            "email": user.email,
            "fullName": user.full_name,
            "role": user.role,
            "licenseNumber": user.license_number or user.id,
            "clinicId": user.clinic_id,
            "twoFactorEnabled": getattr(user, 'two_factor_enabled', False)
        }
    )


@router.post("/verify-login-otp", response_model=AuthResponse)
def verify_login_otp(payload: VerifyLoginOtpRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No clinician account found for this email address."
        )

    now = datetime.now(timezone.utc)
    if (user.failed_login_attempts or 0) >= 3 or (user.locked_until and user.locked_until > now):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is locked due to previous failed attempts. Please complete the password reset flow."
        )

    otp_record = (
        db.query(AuthOtp)
        .filter(AuthOtp.email == email_clean)
        .order_by(AuthOtp.created_at.desc())
        .first()
    )

    if not otp_record or otp_record.otp_code != payload.otp_code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 6-digit sign-in code. Please check the code sent to your email."
        )

    record_exp = otp_record.expires_at.replace(tzinfo=timezone.utc) if otp_record.expires_at.tzinfo is None else otp_record.expires_at
    if record_exp < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sign-in code has expired. Please log in again to request a fresh code."
        )

    # Clean up OTP
    db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()

    if payload.remember_device and payload.device_id:
        user.remembered_device_id = payload.device_id

    user.failed_login_attempts = 0
    user.last_failed_attempt = None
    user.locked_until = None
    user.is_verified = True
    db.commit()

    token = create_jwt_token(user)

    return AuthResponse(
        status="success",
        message="Sign-in verified successfully! Welcome back.",
        token=token,
        user={
            "id": user.id,
            "email": user.email,
            "fullName": user.full_name,
            "role": user.role,
            "licenseNumber": user.license_number or user.id,
            "clinicId": user.clinic_id,
            "twoFactorEnabled": getattr(user, 'two_factor_enabled', False)
        }
    )


@router.post("/forgot-password", response_model=AuthResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No clinician account found for this email address."
        )

    otp_code = generate_numeric_otp(6)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()
    db.add(AuthOtp(email=email_clean, otp_code=otp_code, expires_at=expires_at))
    db.commit()

    send_template_email(
        to_email=email_clean,
        subject=f"Smile Clinic — Password Reset Authorization Code: {otp_code}",
        template_name="password_reset_otp.html",
        context={
            "clinician_name": user.full_name,
            "clinician_email": user.email,
            "reset_code": otp_code,
            "expires_in_minutes": 10
        }
    )

    return AuthResponse(
        status="success",
        message="A 6-digit password reset code has been dispatched to your email.",
        dev_otp=otp_code
    )


@router.post("/reset-password", response_model=AuthResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No clinician account found for this email address."
        )

    now = datetime.now(timezone.utc)
    otp_record = (
        db.query(AuthOtp)
        .filter(AuthOtp.email == email_clean)
        .order_by(AuthOtp.created_at.desc())
        .first()
    )

    if not otp_record or otp_record.otp_code != payload.otp_code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authorization code. Please check the 6-digit code sent to your email."
        )

    record_exp = otp_record.expires_at.replace(tzinfo=timezone.utc) if otp_record.expires_at.tzinfo is None else otp_record.expires_at
    if record_exp < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This authorization code has expired. Please request a new one."
        )

    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters in length."
        )

    # Hash new password and reset all lockouts
    user.hashed_password = hash_password(payload.new_password)
    user.failed_login_attempts = 0
    user.last_failed_attempt = None
    user.locked_until = None
    user.is_verified = True

    # Clean up used OTP
    db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()
    db.commit()

    return AuthResponse(
        status="success",
        message="Password reset successfully! You can now sign in with your new password."
    )


@router.post("/verify-reset-otp", response_model=AuthResponse)
def verify_reset_otp(payload: VerifyResetOtpRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No clinician account found for this email address."
        )

    now = datetime.now(timezone.utc)
    otp_record = (
        db.query(AuthOtp)
        .filter(AuthOtp.email == email_clean)
        .order_by(AuthOtp.created_at.desc())
        .first()
    )

    if not otp_record or otp_record.otp_code != payload.otp_code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 6-digit verification code. Please check the code sent to your email."
        )

    record_exp = otp_record.expires_at.replace(tzinfo=timezone.utc) if otp_record.expires_at.tzinfo is None else otp_record.expires_at
    if record_exp < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification code has expired. Please request a new one."
        )

    return AuthResponse(
        status="success",
        message="Verification code validated successfully."
    )


@router.post("/verify-password", response_model=AuthResponse)
def verify_current_password(payload: VerifyPasswordRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinician record not found."
        )

    if not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This clinician account was created via Google Sign-In and has no existing password. Please use the 'Email Passcode' option to set your password."
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect previous password. Please enter your valid current password."
        )

    return AuthResponse(
        status="success",
        message="Current password verified successfully."
    )


@router.post("/change-password", response_model=AuthResponse)
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinician record not found."
        )

    if not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This clinician account was created via Google Sign-In and has no existing password. Please use the 'Email Passcode' option to set your password."
        )

    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect previous password. Please enter your valid current password."
        )

    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters in length."
        )

    user.hashed_password = hash_password(payload.new_password)
    user.failed_login_attempts = 0
    user.last_failed_attempt = None
    user.locked_until = None
    user.is_verified = True
    db.commit()

    return AuthResponse(
        status="success",
        message="Clinical password updated successfully in the database."
    )


@router.post("/toggle-2fa", response_model=AuthResponse)
def toggle_2fa(payload: Toggle2FaRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinician record not found."
        )

    user.two_factor_enabled = payload.enabled
    db.commit()
    db.refresh(user)

    return AuthResponse(
        status="success",
        message=f"Two-Factor Authentication {'activated' if payload.enabled else 'deactivated'} successfully.",
        user={
            "id": user.id,
            "email": user.email,
            "fullName": user.full_name,
            "role": user.role,
            "licenseNumber": user.license_number or user.id,
            "clinicId": user.clinic_id,
            "twoFactorEnabled": user.two_factor_enabled
        }
    )


@router.post("/google", response_model=AuthResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()

    if user:
        # Existing account: seamlessly link Google, mark email verified, clear locks
        user.is_verified = True
        user.failed_login_attempts = 0
        user.last_failed_attempt = None
        user.locked_until = None
        if payload.device_id:
            user.remembered_device_id = payload.device_id
        db.commit()
        db.refresh(user)

        # If Two-Factor Authentication is enabled, trigger sign-in OTP verification
        if bool(getattr(user, 'two_factor_enabled', False)):
            now = datetime.now(timezone.utc)
            otp_code = generate_numeric_otp(6)
            expires_at = now + timedelta(minutes=10)
            db.query(AuthOtp).filter(AuthOtp.email == email_clean).delete()
            db.add(AuthOtp(email=email_clean, otp_code=otp_code, expires_at=expires_at))
            db.commit()

            send_template_email(
                to_email=email_clean,
                subject=f"Smile Clinic — Sign-In Verification Code: {otp_code}",
                template_name="otp_verification.html",
                context={
                    "clinician_name": user.full_name,
                    "otp_code": otp_code,
                    "expires_in_minutes": 10
                }
            )

            return AuthResponse(
                status="otp_required",
                message="Two-factor verification required. A 6-digit sign-in code has been dispatched to your email.",
                dev_otp=otp_code
            )
    else:
        # New account: provision clinician in PostgreSQL with 2FA off by default
        raw_name = (payload.full_name or "").strip()
        display_name = raw_name if raw_name else email_clean.split("@")[0].capitalize()
        user = User(
            email=email_clean,
            full_name=display_name,
            role="Dentist",
            auth_provider="google",
            clinic_id="CLINIC-MAIN",
            is_verified=True,
            two_factor_enabled=False,
            remembered_device_id=payload.device_id
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_jwt_token(user)

    return AuthResponse(
        status="success",
        message="Google authentication successful.",
        token=token,
        user={
            "id": user.id,
            "email": user.email,
            "fullName": user.full_name,
            "role": user.role,
            "licenseNumber": user.license_number or user.id,
            "clinicId": user.clinic_id,
            "twoFactorEnabled": getattr(user, 'two_factor_enabled', False),
            "authProvider": getattr(user, 'auth_provider', 'google')
        }
    )



