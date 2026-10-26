import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, field_validator

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

class SignupRequest(BaseModel):
    full_name: str
    email: str
    password: str
    phone: Optional[str] = None
    country_code: Optional[str] = None
    role: Optional[str] = "PHARMACIST"
    license_number: Optional[str] = None
    clinic_id: Optional[str] = "CLINIC-MAIN"

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

class AuthResponse(BaseModel):
    status: str
    message: str
    token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    dev_otp: Optional[str] = None
    attempts_remaining: Optional[int] = None
    is_locked: Optional[bool] = None
