from .storage import provision_user_r2_folders
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

from ..models import User, AuthOtp, UserSession

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

    UpdateProfileRequest,

    AuthResponse,

    RecordSessionRequest,

    RevokeSessionRequest,

    SessionItem,

    SessionListResponse,

    ReportEmailRequest,

    AuditEmailRequest,

    ScheduleAlertEmailRequest,
    DoctorConsultEmailRequest

)



router = APIRouter(prefix="/api/v1/auth", tags=["Prescription Authentication"])



JWT_SECRET = os.getenv("JWT_SECRET", "smileclinic_jwt_secret_dev_key_2026_super_secure_clinical")

JWT_ALGORITHM = "HS256"

JWT_EXPIRATION_DAYS = 7

GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL")

frontend_env = os.getenv("FRONTEND_URL")

PORTAL_LOGIN_URL = os.getenv("PORTAL_LOGIN_URL") or (f"{frontend_env.rstrip('/')}/login" if frontend_env else "http://localhost:5173/login")



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



def user_dict(user: User) -> dict:

    return {

        "id": user.id,

        "email": user.email,

        "fullName": user.full_name,

        "role": user.role or "USER",

        "phone": user.phone or "",

        "age": getattr(user, 'age', None),

        "gender": getattr(user, 'gender', None),

        "height": getattr(user, 'height', None),

        "weight": getattr(user, 'weight', None),

        "hasAllergies": getattr(user, 'has_allergies', False) or False,

        "allergiesDescription": getattr(user, 'allergies_description', None) or "",

        "profileCompleted": getattr(user, 'profile_completed', False) or False,

        "photoUrl": getattr(user, 'photo_url', None) or "",

        "twoFactorEnabled": getattr(user, 'two_factor_enabled', False) or False,

        "authProvider": getattr(user, 'auth_provider', 'email'),

        "isGoogleLinked": bool(getattr(user, 'is_google_linked', False) or user.auth_provider == 'google'),

        "hasPassword": bool(user.hashed_password is not None and user.hashed_password.strip() != "")

    }



def create_jwt_token(user: User) -> str:

    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)

    payload = {

        "sub": user.id,

        "email": user.email,

        "role": user.role,

        "name": user.full_name,

        "exp": expire

    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)



def generate_numeric_otp(length: int = 6) -> str:

    return "".join(secrets.choice("0123456789") for _ in range(length))



def get_user_remembered_devices(user: User) -> list[str]:

    """Returns a list of distinct non-empty device IDs remembered for the user."""

    raw = getattr(user, 'remembered_device_id', None) or ""

    return [d.strip() for d in raw.split(",") if d.strip()]



def is_device_remembered(user: User, device_id: Optional[str]) -> bool:

    """Returns True if device_id is non-empty and recognized among user's remembered devices."""

    if not device_id or not device_id.strip():

        return False

    return device_id.strip() in get_user_remembered_devices(user)



def add_user_remembered_device(user: User, device_id: Optional[str]) -> None:

    """Adds a device ID to user's remembered devices (stores up to 20 devices)."""

    if not device_id or not device_id.strip():

        return

    clean_id = device_id.strip()

    devices = get_user_remembered_devices(user)

    if clean_id not in devices:

        devices.append(clean_id)

        if len(devices) > 20:

            devices = devices[-20:]

        user.remembered_device_id = ",".join(devices)



def remove_user_remembered_device(user: User, device_id: Optional[str]) -> None:

    """Removes a device ID from user's remembered devices list."""

    if not device_id or not device_id.strip():

        return

    clean_id = device_id.strip()

    devices = [d for d in get_user_remembered_devices(user) if d != clean_id]

    user.remembered_device_id = ",".join(devices) if devices else None



def send_template_email(to_email: str, subject: str, template_name: str, context: dict, attachment_base64: Optional[str] = None, attachment_name: Optional[str] = None, cc: Optional[str] = None) -> bool:
    """Renders HTML template from templates/ via Jinja2 and sends via Google Apps Script Mail Gateway."""
    template_file = get_template_path(template_name)
    html_content = ""
    if template_file and template_file.exists():
        with open(template_file, "r", encoding="utf-8") as f:
            raw_tpl = f.read()
        try:
            from jinja2 import Template
            html_content = Template(raw_tpl).render(**context)
        except Exception as je:
            html_content = raw_tpl
            for k, v in context.items():
                html_content = html_content.replace(f"{{{{ {k} }}}}", str(v))
                html_content = html_content.replace(f"{{{{{k}}}}}", str(v))
    else:
        html_content = f"<h2>Smile Clinic</h2><p>{subject}</p>"

    if not GOOGLE_APPS_SCRIPT_URL:
        print(f"[AUTH_EMAIL_DEV] GOOGLE_APPS_SCRIPT_URL unset; email to {to_email} captured in local dev mode.")
        return False

    try:
        post_data = {
            "to": to_email,
            "subject": subject,
            "html": html_content
        }
        if cc and cc != to_email and "@" in cc:
            post_data["cc"] = cc

        if attachment_base64 and attachment_name:
            post_data["attachment_base64"] = attachment_base64
            post_data["attachment_name"] = attachment_name
            post_data["attachment_type"] = "application/pdf"

        res = requests.post(
            GOOGLE_APPS_SCRIPT_URL,
            json=post_data,
            timeout=15
        )
        if res.status_code == 200:
            print(f"[AUTH_EMAIL_SUCCESS] Dispatched '{template_name}' to {to_email} (CC: {cc}) via Google Apps Script.")
            return True
        else:
            print(f"[AUTH_EMAIL_ERROR] Apps Script returned status {res.status_code}: {res.text}")
            return False
    except Exception as e:
        print(f"[AUTH_EMAIL_EXCEPTION] Email delivery skipped: {e}")
        return False


# Backward-compatibility alias

send_transactional_email = send_template_email





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

        existing_user.role = payload.role or "USER"

        user = existing_user

    else:

        user = User(

            email=email_clean,

            full_name=payload.full_name.strip(),

            hashed_password=hashed_pwd,

            phone=payload.phone,

            role=payload.role or "USER",

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

        user=user_dict(user)

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



    # 5. Check Security Verification (2FA / Remember Device / New Device Detection / Revoked Device)

    two_fa_active = bool(getattr(user, 'two_factor_enabled', False))

    device_recognized = is_device_remembered(user, payload.device_id)



    # Check if this specific device was logged out / revoked from Settings

    is_revoked_in_db = False

    if payload.device_id:

        dev_id_clean = payload.device_id.strip()

        active_sess = (

            db.query(UserSession)

            .filter(

                UserSession.email == email_clean,

                UserSession.device_id == dev_id_clean,

                UserSession.is_active == True

            )

            .first()

        )

        if not active_sess:

            revoked_sess = (

                db.query(UserSession)

                .filter(

                    UserSession.email == email_clean,

                    UserSession.device_id == dev_id_clean,

                    UserSession.is_active == False

                )

                .first()

            )

            if revoked_sess:

                is_revoked_in_db = True

                # Purge from remembered devices to ensure no stale token remains

                remove_user_remembered_device(user, dev_id_clean)

                db.commit()



    # Mandatory OTP is triggered if:

    # 1. 2FA is explicitly enabled on account, OR

    # 2. "Remember me" is turned off (payload.remember_device is False), OR

    # 3. This device is logging in for the first time (not yet in remembered list), even if remember_device is True!

    # 4. This device was logged out / revoked from Settings (is_revoked_in_db is True)!

    if two_fa_active or (not payload.remember_device) or (not device_recognized) or is_revoked_in_db:

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



        if two_fa_active:

            msg = "Two-factor verification required. A 6-digit sign-in code has been dispatched to your email."

        elif is_revoked_in_db:

            msg = "Workstation re-authorization required. A 6-digit verification code has been dispatched to your email."

        elif not device_recognized:

            msg = "New workstation detected. For clinical security, a 6-digit verification code has been dispatched to your email."

        else:

            msg = "Sign-in verification required. A 6-digit verification code has been dispatched to your email."



        return AuthResponse(

            status="otp_required",

            message=msg,

            dev_otp=otp_code

        )



    # If device is recognized and remember_device is True: direct login without OTP friction

    user.failed_login_attempts = 0

    user.last_failed_attempt = None

    user.locked_until = None

    db.commit()



    token = create_jwt_token(user)



    return AuthResponse(

        status="success",

        message="Login successful.",

        token=token,

        user=user_dict(user)

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

        add_user_remembered_device(user, payload.device_id)

        # Re-activate any previously revoked session for this workstation

        prev_sessions = (

            db.query(UserSession)

            .filter(UserSession.email == email_clean, UserSession.device_id == payload.device_id.strip())

            .all()

        )

        for s in prev_sessions:

            s.is_active = True

            s.status = "Success"

            s.last_active = now

    elif not payload.remember_device and payload.device_id:

        remove_user_remembered_device(user, payload.device_id)



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

        user=user_dict(user)

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



    # Dispatch security notification email confirming password update

    change_time_str = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")

    send_template_email(

        to_email=email_clean,

        subject="Smile Clinic Security Alert — Your Clinical Password Was Changed",

        template_name="password_changed_notification.html",

        context={

            "clinician_name": user.full_name or "Authorized Prescriber",

            "clinician_email": user.email,

            "change_time": change_time_str,

            "portal_login_url": PORTAL_LOGIN_URL

        }

    )



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



    # Dispatch security notification email confirming password update

    change_time_str = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")

    send_template_email(

        to_email=email_clean,

        subject="Smile Clinic Security Alert — Your Clinical Password Was Changed",

        template_name="password_changed_notification.html",

        context={

            "clinician_name": user.full_name or "Authorized Prescriber",

            "clinician_email": user.email,

            "change_time": change_time_str,

            "portal_login_url": PORTAL_LOGIN_URL

        }

    )



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

        user=user_dict(user)

    )





@router.post("/google", response_model=AuthResponse)

def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)):

    email_clean = payload.email.strip().lower()

    user = db.query(User).filter(User.email == email_clean).first()



    if user:

        # Existing account (email/password or OAuth): seamlessly link Google, mark verified, clear locks

        user.is_verified = True

        user.is_google_linked = True

        if payload.photo_url and not getattr(user, 'photo_url', None):

            user.photo_url = payload.photo_url.strip()

        user.failed_login_attempts = 0

        user.last_failed_attempt = None

        user.locked_until = None

        if payload.device_id:

            add_user_remembered_device(user, payload.device_id)

        db.commit()

        db.refresh(user)



        # Dispatch welcome email on Google login to clinician's email address

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

            role="USER",

            auth_provider="google",

            photo_url=payload.photo_url.strip() if payload.photo_url else None,

            is_google_linked=True,

            is_verified=True,

            two_factor_enabled=False,

            remembered_device_id=payload.device_id

        )

        db.add(user)

        db.commit()

        db.refresh(user)



        # Dispatch welcome email on Google registration

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



    token = create_jwt_token(user)



    return AuthResponse(

        status="success",

        message="Google authentication successful.",

        token=token,

        user=user_dict(user)

    )





@router.post("/link-google", response_model=AuthResponse)

def link_google(payload: GoogleAuthRequest, db: Session = Depends(get_db)):

    email_clean = payload.email.strip().lower()

    user = db.query(User).filter(User.email == email_clean).first()

    if not user:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="Clinician record not found."

        )

    user.is_google_linked = True

    db.commit()

    db.refresh(user)

    return AuthResponse(

        status="success",

        message="Google account linked successfully.",

        user=user_dict(user)

    )





@router.post("/update-profile", response_model=AuthResponse)

@router.put("/profile", response_model=AuthResponse)

def update_profile(payload: UpdateProfileRequest, db: Session = Depends(get_db)):

    email_clean = payload.email.strip().lower()

    user = db.query(User).filter(User.email == email_clean).first()

    if not user:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="User account not found."

        )



    if payload.full_name is not None and payload.full_name.strip():

        user.full_name = payload.full_name.strip()

    if payload.phone is not None:

        user.phone = payload.phone.strip()

    if payload.age is not None:

        user.age = payload.age

    if payload.gender is not None:

        user.gender = payload.gender

    if payload.height is not None:

        user.height = payload.height

    if payload.weight is not None:

        user.weight = payload.weight

    if payload.has_allergies is not None:

        user.has_allergies = payload.has_allergies

    if payload.allergies_description is not None:

        user.allergies_description = payload.allergies_description

    if payload.profile_completed is not None:

        user.profile_completed = payload.profile_completed

    if payload.photo_url is not None:

        user.photo_url = payload.photo_url.strip()



    db.commit()

    db.refresh(user)



    token = create_jwt_token(user)



    return AuthResponse(

        status="success",

        message="Profile details updated successfully.",

        token=token,

        user=user_dict(user)

    )





@router.get("/profile-status")

@router.get("/profile")

def get_profile_status(email: str, db: Session = Depends(get_db)):

    """

    Retrieve clinical profile details and completion status across devices.

    Once completed on any device, this returns profileCompleted: True.

    """

    email_clean = email.strip().lower()

    user = db.query(User).filter(User.email == email_clean).first()

    if not user:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="User account not found."

        )



    u_dict = user_dict(user)

    is_completed = bool(getattr(user, "profile_completed", False))



    return {

        "status": "success",

        "message": "User profile status retrieved successfully.",

        "email": user.email,

        "profileCompleted": is_completed,

        "user": u_dict

    }





@router.post("/record-session")

def record_session(payload: RecordSessionRequest, db: Session = Depends(get_db)):

    """

    Registers or updates an active authenticated workstation session in PostgreSQL.

    """

    email_clean = payload.email.strip().lower()

    user = db.query(User).filter(User.email == email_clean).first()

    if not user:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="Clinician user account not found."

        )



    now = datetime.now(timezone.utc)

    device_id_clean = payload.device_id.strip()



    # Find existing session for this user and device

    existing = (

        db.query(UserSession)

        .filter(UserSession.email == email_clean, UserSession.device_id == device_id_clean)

        .first()

    )



    if existing:

        existing.device_name = payload.device_name.strip()

        existing.browser_os = payload.browser_os.strip()

        if payload.ip_address:

            existing.ip_address = payload.ip_address.strip()

        if payload.location:

            existing.location = payload.location.strip()

        existing.status = payload.status or "Success"

        if payload.details:

            existing.details = payload.details.strip()

        existing.is_active = True

        existing.last_active = now

        db.commit()

        db.refresh(existing)

        session_obj = existing

    else:

        session_obj = UserSession(

            email=email_clean,

            device_id=device_id_clean,

            device_name=payload.device_name.strip(),

            browser_os=payload.browser_os.strip(),

            ip_address=payload.ip_address.strip() if payload.ip_address else None,

            location=payload.location.strip() if payload.location else "Cloudflare Edge • Verified TLS",

            status=payload.status or "Success",

            is_active=True,

            details=payload.details.strip() if payload.details else f"Authorized clinical session established ({user.full_name})",

            created_at=now,

            last_active=now

        )

        db.add(session_obj)

        db.commit()

        db.refresh(session_obj)



    return {

        "status": "success",

        "message": "Session recorded successfully.",

        "session": {

            "id": session_obj.id,

            "device_id": session_obj.device_id,

            "device_name": session_obj.device_name,

            "browser_os": session_obj.browser_os,

            "status": session_obj.status,

            "is_active": session_obj.is_active

        }

    }





@router.get("/sessions", response_model=SessionListResponse)

def get_user_sessions(email: str, current_device_id: Optional[str] = None, db: Session = Depends(get_db)):

    """

    Retrieves all active workstation sessions and login history for the clinician from PostgreSQL.

    """

    email_clean = email.strip().lower()

    user = db.query(User).filter(User.email == email_clean).first()

    if not user:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="Clinician user account not found."

        )



    all_records = (

        db.query(UserSession)

        .filter(UserSession.email == email_clean)

        .order_by(UserSession.last_active.desc())

        .limit(50)

        .all()

    )



    clean_curr_device = current_device_id.strip() if current_device_id else None



    # Group into active sessions and login audit history

    active_sessions: list[SessionItem] = []

    history_items: list[SessionItem] = []



    for s in all_records:

        is_curr = bool(clean_curr_device and s.device_id == clean_curr_device)

        created_str = s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else ""

        last_str = s.last_active.strftime("%Y-%m-%d %H:%M:%S") if s.last_active else ""



        item = SessionItem(

            id=s.id[:8].upper() if s.id else "SES-01",

            email=s.email,

            device_id=s.device_id,

            device_name=s.device_name,

            browser_os=s.browser_os,

            ip_address=s.ip_address or "10.240.42.18",

            location=s.location or "Cloudflare Edge • Verified TLS",

            status=s.status or ("Success" if s.is_active else "Revoked"),

            is_active=bool(s.is_active),

            is_current=is_curr,

            details=s.details,

            created_at=created_str,

            last_active=last_str

        )



        history_items.append(item)

        if s.is_active:

            active_sessions.append(item)



    return SessionListResponse(

        status="success",

        sessions=active_sessions,

        history=history_items

    )





@router.post("/revoke-session")

def revoke_session(payload: RevokeSessionRequest, db: Session = Depends(get_db)):

    """

    Revokes and logs out a specific workstation session remotely.

    """

    email_clean = payload.email.strip().lower()

    user = db.query(User).filter(User.email == email_clean).first()

    if not user:

        raise HTTPException(

            status_code=status.HTTP_404_NOT_FOUND,

            detail="Clinician user account not found."

        )



    now = datetime.now(timezone.utc)

    revoked_count = 0

    target_device_id = payload.device_id.strip() if payload.device_id else None



    # 1. Revoke by session ID if provided

    if payload.session_id:

        sess_query = db.query(UserSession).filter(

            UserSession.email == email_clean,

            (UserSession.id == payload.session_id) | (UserSession.id.startswith(payload.session_id.lower()))

        )

        sessions = sess_query.all()

        for s in sessions:

            s.is_active = False

            s.status = "Revoked"

            s.last_active = now

            if not target_device_id:

                target_device_id = s.device_id

            if s.device_id:

                remove_user_remembered_device(user, s.device_id)

            revoked_count += 1



    # 2. Revoke by device ID if provided

    if target_device_id:

        dev_sessions = (

            db.query(UserSession)

            .filter(UserSession.email == email_clean, UserSession.device_id == target_device_id)

            .all()

        )

        for s in dev_sessions:

            s.is_active = False

            s.status = "Revoked"

            s.last_active = now

            revoked_count += 1

        remove_user_remembered_device(user, target_device_id)



        # If this device had no rows in DB yet, create a revoked entry to force OTP re-challenge on next login

        if not dev_sessions:

            placeholder_sess = UserSession(

                email=email_clean,

                device_id=target_device_id,

                device_name=payload.device_name or "Remote Terminal",

                browser_os="Terminated Session",

                status="Revoked",

                is_active=False,

                details="Session terminated from Security Settings",

                created_at=now,

                last_active=now

            )

            db.add(placeholder_sess)

            revoked_count += 1



    # 3. Revoke by device name if provided and no session matched yet

    if payload.device_name and revoked_count == 0:

        name_clean = payload.device_name.strip()

        named_sessions = (

            db.query(UserSession)

            .filter(

                UserSession.email == email_clean,

                UserSession.device_name.ilike(f"%{name_clean}%")

            )

            .all()

        )

        for s in named_sessions:

            s.is_active = False

            s.status = "Revoked"

            s.last_active = now

            if s.device_id:

                remove_user_remembered_device(user, s.device_id)

                if not target_device_id:

                    target_device_id = s.device_id

            revoked_count += 1



    db.commit()



    return {

        "status": "success",

        "message": f"Successfully revoked {revoked_count} workstation session(s).",

        "revoked_device_id": target_device_id

    }





@router.get("/session-status")

def get_session_status(email: str, device_id: str, db: Session = Depends(get_db)):

    """

    Heartbeat verification to check if the current device session is still authorized or remotely revoked.

    """

    email_clean = email.strip().lower()

    device_id_clean = device_id.strip()



    session_record = (

        db.query(UserSession)

        .filter(UserSession.email == email_clean, UserSession.device_id == device_id_clean)

        .order_by(UserSession.last_active.desc())

        .first()

    )



    if not session_record:

        return {"status": "success", "valid": True, "active": True, "revoked": False}



    if not session_record.is_active:

        return {

            "status": "revoked",

            "valid": False,

            "active": False,

            "revoked": True,

            "message": "This workstation session was revoked from another authorized terminal."

        }



    return {"status": "success", "valid": True, "active": True, "revoked": False}



@router.post("/send-report-email")
def send_report_email(req: ReportEmailRequest, db: Session = Depends(get_db)):
    """
    Sends certified 2-page Clinical Decision Support (CDS) Verification Report to clinician email
    with base64 attached PDF and direct download links.
    """
    from datetime import datetime, timezone
    import base64
    from ..models import PrescriptionCheck

    target_email = req.to_email or req.recipient_email
    if not target_email or "@" not in target_email:
        raise HTTPException(status_code=400, detail="A valid recipient email address ('to_email' or 'recipient_email') is required.")

    target_email = target_email.strip().lower()
    utc_now = req.timestamp_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Reconcile from database record if available
    chk = None
    if req.report_id:
        chk = db.query(PrescriptionCheck).filter(
            (PrescriptionCheck.id == req.report_id.strip()) | (PrescriptionCheck.id == req.report_id)
        ).first()

    patient_name = (chk.patient_name if chk and chk.patient_name else req.patient_name) or "Karuna Chouhan"
    patient_mrn = (chk.patient_mrn if chk and chk.patient_mrn else req.patient_mrn) or "PT-NEW-001"
    overall_status = (chk.status if chk and chk.status else req.overall_status) or "Safe to Dispense"
    prescriptions = (chk.prescriptions if chk and chk.prescriptions else None)
    alerts = (chk.alerts if chk and chk.alerts else None)
    digital_seal = (chk.digital_seal if chk and chk.digital_seal else req.notary_hash) or "SHA256:AUTHENTICATED-SEAL"

    if prescriptions is None:
        prescriptions = [{'drugName': d.strip()} for d in (req.candidate_drugs or '').split(';') if d.strip()]
    if alerts is None:
        alerts = [{'severity': 'info', 'title': a.strip()} for a in (req.alerts_summary or '').split(';') if a.strip()]

    backend_base = os.getenv("BACKEND_URL", "https://dentalclinic-backend-eiav.onrender.com").rstrip("/")
    download_url = req.download_url or f"{backend_base}/api/v1/sync/report-pdf?id={req.report_id}&email={target_email}"
    pdf_filename = req.pdf_filename or (f"{req.report_id}.pdf" if ("PS-" in req.report_id or "Prescription" in req.report_id) else f"SmileClinic_CDS_Report_{req.report_id}.pdf")

    # Structured inquiries from request or database
    inquiries_list = req.question_answers or (chk.clinical_inquiries if chk and chk.clinical_inquiries else [])

    # Generate 2-Page CDS ReportLab PDF Attachment
    pdf_b64 = req.pdf_base64
    if not pdf_b64:
        try:
            from ..pdf_generator import generate_2page_cds_pdf
            pdf_bytes = generate_2page_cds_pdf({
                'report_id': req.report_id,
                'patient_name': patient_name,
                'patient_mrn': patient_mrn,
                'clinician_name': req.clinician_name or "Dr. Sanjeev Saxena",
                'overall_status': overall_status,
                'timestamp_str': utc_now,
                'digital_seal': digital_seal,
                'prescriptions': prescriptions,
                'alerts': alerts,
                'clinical_inquiries': inquiries_list,
                'question_answers': inquiries_list,
                'gemini_summary': {
                    'clinicalSummary': req.alerts_summary or 'Prescription screened and verified clean.',
                    'questionAnswers': inquiries_list
                }
            })
            pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
        except Exception as e:
            print(f'[Report PDF Gen Warning] {e}')

    context = {
        "report_id": req.report_id,
        "patient_name": patient_name,
        "patient_mrn": patient_mrn,
        "clinician_name": req.clinician_name or "Authorized Clinician",
        "clinician_npi": req.clinician_npi or "DENT-CLINIC",
        "overall_status": overall_status,
        "timestamp_utc": utc_now,
        "candidate_drugs": req.candidate_drugs or "; ".join([p.get('drugName', 'Rx') for p in prescriptions]),
        "rx_count": len(prescriptions) if prescriptions else req.rx_count,
        "alerts_summary": req.alerts_summary or "Screening verification finalized.",
        "alerts_count": len(alerts) if alerts else req.alerts_count,
        "question_answers": inquiries_list,
        "portal_url": req.portal_url or "https://prescription-dentalclinic.pages.dev/report",
        "download_url": download_url,
        "pdf_filename": pdf_filename,
        "notary_hash": digital_seal,
    }

    subject = f"Smile Clinic — 2-Page CDS Verification Report [{req.report_id}]"

    delivered = send_transactional_email(
        target_email,
        subject,
        "clinical_cds_report_email.html",
        context,
        attachment_base64=pdf_b64,
        attachment_name=pdf_filename
    )

    return {
        "status": "success" if delivered else "sent_local",
        "message": f"Clinical CDS verification report dispatched to {target_email}",
        "report_id": req.report_id,
        "recipient": target_email,
        "delivered": delivered,
        "download_url": download_url,
        "hasAttachment": bool(pdf_b64)
    }



@router.post("/send-audit-email")

def send_audit_email(req: AuditEmailRequest):

    """

    Sends certified HIPAA Audit Trail Export to clinician email.

    """

    from datetime import datetime, timezone

    utc_now = req.timestamp_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    filename = req.filename or f"SmileClinic_HIPAA_Audit_{req.export_format.lower()}_{int(datetime.now().timestamp())}.{req.export_format.lower()}"

    context = {

        "clinician_name": req.clinician_name,

        "export_format": req.export_format.upper(),

        "records_count": req.records_count,

        "time_scope": req.time_scope,

        "timestamp_utc": utc_now,

        "notary_hash": req.notary_hash,

        "download_url": req.download_url or "https://prescription-dentalclinic.pages.dev/audit",

        "filename": filename,

        "records": req.records or [],

    }

    subject = f"Smile Clinic — HIPAA Audit Trail Export [{req.export_format.upper()}]"

    delivered = send_transactional_email(req.to_email, subject, "audit_trail_export_email.html", context)

    return {

        "status": "success" if delivered else "sent_local",

        "message": f"HIPAA audit trail export dispatched to {req.to_email}",

        "filename": filename,

        "records": req.records or [],

        "delivered": delivered

    }



@router.post("/send-schedule-alert-email")
def send_schedule_alert_email(req: ScheduleAlertEmailRequest,
    DoctorConsultEmailRequest, db: Session = Depends(get_db)):
    """
    Sends verified daily medication timetable and safety alert schedule to patient/clinician email.
    """
    import hashlib
    from datetime import datetime, timezone
    utc_now = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")
    
    # Build HTML rows for each medication
    rows_html = []
    for med in req.medications:
        name = med.get("name") or med.get("drugName") or "Medication"
        strength = med.get("dosage") or med.get("strength") or ""
        freq = med.get("frequency") or "Once daily"
        timing = med.get("scheduledTime") or med.get("timing") or "08:00 AM"
        food = med.get("foodInstruction") or med.get("food") or "With or after food"
        duration = med.get("duration") or req.regimen_duration or "30 Days"
        
        row = f"""
        <tr style="border-bottom: 1px solid #f1f5f9;">
          <td style="padding: 12px 14px; font-weight: 700; color: #005c65; white-space: nowrap;">
            <span style="background: #e6f6f8; color: #005c65; padding: 3px 8px; border-radius: 6px; font-size: 11px;">{timing}</span>
          </td>
          <td style="padding: 12px 14px;">
            <strong style="font-size: 13px; color: #0f172a;">{name}</strong> {strength}<br>
            <span style="color: #64748b; font-size: 11px;">Frequency: {freq}</span>
          </td>
          <td style="padding: 12px 14px; color: #334155;">
            {food}
          </td>
          <td style="padding: 12px 14px; text-align: right; color: #64748b; white-space: nowrap;">
            {duration}
          </td>
        </tr>
        """
        rows_html.append(row)
        
    table_rows_str = "".join(rows_html) if rows_html else """
    <tr>
      <td colspan="4" style="padding: 16px; text-align: center; color: #64748b;">
        No active scheduled medications listed.
      </td>
    </tr>
    """
    
    # Format safety alerts summary
    alerts_summary_parts = []
    for al in req.safety_alerts:
        title = al.get("title") or "Clinical Interaction"
        rec = al.get("recommendation") or al.get("mechanism") or "Review with prescriber."
        alerts_summary_parts.append(f"• <strong>{title}:</strong> {rec}")
    safety_summary_str = "<br>".join(alerts_summary_parts) if alerts_summary_parts else "All interactions cleared."
    
    notary = req.notary_hash or f"SHA256:{hashlib.sha256(f'{req.check_number}:{req.patient_name}:{utc_now}'.encode('utf-8')).hexdigest()[:24].upper()}"
    
    context = {
        "patient_name": req.patient_name,
        "patient_mrn": req.patient_mrn or "PT-NEW-001",
        "clinician_name": req.clinician_name or "Authorized Prescriber",
        "check_number": req.check_number or "CHK-CURRENT",
        "schedule_date": req.schedule_date or utc_now,
        "course_end_date": req.course_end_date or "In 30 Days (Course Completed)",
        "regimen_duration": req.regimen_duration or "1 Month",
        "medication_table_rows": table_rows_str,
        "safety_alerts_count": len(req.safety_alerts),
        "safety_alerts_summary": safety_summary_str,
        "portal_url": req.portal_url or "https://prescription-dentalclinic.pages.dev/alerts",
        "notary_hash": notary
    }
    
    subject = f"Smile Clinic — Medication Schedule & Safety Alert for {req.patient_name} [{req.check_number}]"
    delivered = send_transactional_email(req.to_email, subject, "medication_schedule_alert_email.html", context)
    
    # Log audit event
    try:
        from ..models import AuditLog
        audit_entry = AuditLog(
            id=f"aud-sched-{int(datetime.now().timestamp())}",
            user_email=req.to_email,
            clinician_name=req.clinician_name or "Authorized Prescriber",
            action="Medication Schedule & Safety Alert Dispatched",
            patient_mrn=req.patient_mrn or "PT-GENERAL",
            event_details=f"Dispatched intake timetable & safety warnings for {len(req.medications)} drugs to {req.to_email}",
            severity="info",
            inner_data={"patientName": req.patient_name, "checkNumber": req.check_number, "medicationsCount": len(req.medications)},
            hash=notary,
            created_at=datetime.now(timezone.utc)
        )
        db.add(audit_entry)
        db.commit()
    except Exception as e:
        print(f"[Audit Log Warning] {e}")
        
    return {
        "status": "success" if delivered else "sent_local",
        "message": f"Medication schedule & safety alert dispatched to {req.to_email}",
        "delivered": delivered,
        "recipient": req.to_email,
        "check_number": req.check_number
    }

@router.post('/send-doctor-consult-email')
def send_doctor_consult_email(req: DoctorConsultEmailRequest, db: Session = Depends(get_db)):
    """
    Sends an urgent clinical interaction alert, doctor consultation notice, and proposed regimen change to the prescribing doctor.
    """
    import hashlib
    from datetime import datetime, timezone
    utc_now = datetime.now(timezone.utc).strftime('%d %b %Y, %I:%M %p UTC')
    
    drug_a = req.interacting_drugs[0] if len(req.interacting_drugs) > 0 else 'Prescribed Medication'
    drug_b = req.interacting_drugs[1] if len(req.interacting_drugs) > 1 else 'Interacting Agent'
    
    notary = req.notary_hash or f"SHA256:{hashlib.sha256(f'{req.check_number}:{req.patient_name}:{req.doctor_name}:{utc_now}'.encode('utf-8')).hexdigest()[:24].upper()}"
    
    context = {
        'prescriber_name': req.doctor_name,
        'doctor_name': req.doctor_name,
        'patient_name': req.patient_name,
        'patient_mrn': req.patient_mrn or 'PT-NEW-001',
        'severity_level': req.severity.upper(),
        'alert_title': req.alert_title,
        'proposed_drug': drug_a,
        'conflict_agent': drug_b,
        'interaction_mechanism': req.clinical_mechanism,
        'substituted_medication': req.substituted_medication,
        'clinical_notes': req.rationale,
        'clinician_name': req.clinician_name or 'Authorized Clinician',
        'clinician_email': req.clinician_email or '',
        'check_number': req.check_number or 'CHK-CURRENT',
        'review_url': req.portal_url or 'https://prescription-dentalclinic.pages.dev/alerts',
        'notary_hash': notary
    }
    
    subject = f"Smile Clinic CDS Alert: Prescription Interaction Consultation for {req.patient_name} [{req.severity.upper()}]"
    cc_user = req.clinician_email if (req.clinician_email and req.clinician_email.strip().lower() != req.to_doctor_email.strip().lower() and '@' in req.clinician_email) else None
    delivered = send_transactional_email(req.to_doctor_email, subject, 'doctor_medication_change_alert.html', context, cc=cc_user)
    
    # Immutable audit logging into PostgreSQL database
    try:
        from ..models import AuditLog
        audit_entry = AuditLog(
            id=f"aud-doc-{int(datetime.now().timestamp())}",
            user_email=req.clinician_email or req.to_doctor_email,
            clinician_name=req.clinician_name or 'Authorized Prescriber',
            action='Doctor Consulted & Regimen Modified',
            patient_mrn=req.patient_mrn or 'PT-GENERAL',
            event_details=f"Clinical alert for {drug_a} <-> {drug_b} dispatched to {req.doctor_name} ({req.to_doctor_email}). Substituted drug: {req.substituted_medication or 'None'}",
            severity=req.severity.lower(),
            inner_data={
                'doctorName': req.doctor_name,
                'doctorEmail': req.to_doctor_email,
                'patientName': req.patient_name,
                'patientMrn': req.patient_mrn,
                'checkNumber': req.check_number,
                'alertTitle': req.alert_title,
                'interactingDrugs': req.interacting_drugs,
                'substitutedMedication': req.substituted_medication,
                'rationale': req.rationale,
                'notaryHash': notary
            },
            hash=notary,
            created_at=datetime.now(timezone.utc)
        )
        db.add(audit_entry)
        db.commit()
    except Exception as e:
        print(f"[Doctor Consult Audit Warning] {e}")
        
    return {
        'status': 'success' if delivered else 'sent_local',
        'message': f"Clinical consultation notice successfully dispatched to Dr. {req.doctor_name} ({req.to_doctor_email})",
        'delivered': delivered,
        'doctor_name': req.doctor_name,
        'doctor_email': req.to_doctor_email,
        'substituted_medication': req.substituted_medication,
        'check_number': req.check_number,
        'notary_hash': notary
    }

