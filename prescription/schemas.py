import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, field_validator

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

class SignupRequest(BaseModel):
    full_name: str
    email: str
    password: str
    phone: Optional[str] = None
    country_code: Optional[str] = None
    role: Optional[str] = "USER"

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

class VerifyOtpRequest(BaseModel):
    email: str
    otp_code: str

class ResendOtpRequest(BaseModel):
    email: str

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_device: Optional[bool] = True
    device_id: Optional[str] = None

class VerifyLoginOtpRequest(BaseModel):
    email: str
    otp_code: str
    remember_device: Optional[bool] = False
    device_id: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

class ResetPasswordRequest(BaseModel):
    email: str
    otp_code: str
    new_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

class Toggle2FaRequest(BaseModel):
    email: str
    enabled: bool

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        return clean

class GoogleAuthRequest(BaseModel):
    email: str
    full_name: Optional[str] = "Clinician"
    id_token: Optional[str] = None
    photo_url: Optional[str] = None
    device_id: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

class VerifyResetOtpRequest(BaseModel):
    email: str
    otp_code: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

class VerifyPasswordRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

class ChangePasswordRequest(BaseModel):
    email: str
    current_password: str
    new_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

class UpdateProfileRequest(BaseModel):
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    has_allergies: Optional[bool] = False
    allergies_description: Optional[str] = None
    profile_completed: Optional[bool] = True
    photo_url: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

class AuthResponse(BaseModel):
    status: str
    message: str
    token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    dev_otp: Optional[str] = None
    attempts_remaining: Optional[int] = None
    is_locked: Optional[bool] = None

class RecordSessionRequest(BaseModel):
    email: str
    device_id: str
    device_name: str
    browser_os: str
    ip_address: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = "Success"
    details: Optional[str] = None

class RevokeSessionRequest(BaseModel):
    email: str
    device_id: Optional[str] = None
    session_id: Optional[str] = None
    device_name: Optional[str] = None

class SessionItem(BaseModel):
    id: str
    email: str
    device_id: str
    device_name: str
    browser_os: str
    ip_address: Optional[str] = None
    location: Optional[str] = None
    status: str
    is_active: bool
    is_current: bool = False
    details: Optional[str] = None
    created_at: str
    last_active: str

class SessionListResponse(BaseModel):
    status: str
    sessions: List[SessionItem]
    history: List[SessionItem]
