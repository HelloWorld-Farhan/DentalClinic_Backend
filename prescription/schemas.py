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



class ReportEmailRequest(BaseModel):
    to_email: Optional[str] = None
    recipient_email: Optional[str] = None
    report_id: Optional[str] = 'REP-2026-0419-892'
    patient_name: Optional[str] = 'Anonymous Patient'
    patient_mrn: Optional[str] = 'PT-MRN-9281'
    clinician_name: Optional[str] = 'Active Clinician'
    clinician_npi: Optional[str] = 'NPI-1092837482'
    overall_status: Optional[str] = 'Safe to Dispense'
    timestamp_utc: Optional[str] = None
    candidate_drugs: Optional[str] = 'Standard Dental Therapy'
    rx_count: Optional[int] = 1
    alerts_summary: Optional[str] = 'No Contraindicated Interactions Detected.'
    alerts_count: Optional[int] = 0
    portal_url: Optional[str] = 'https://prescription-dentalclinic.pages.dev/report'
    download_url: Optional[str] = None
    pdf_filename: Optional[str] = None
    pdf_base64: Optional[str] = None
    notary_hash: Optional[str] = 'SHA256-4f8b9e892c21ad8310c8ff0e34a7812bc88'

    @field_validator('to_email', 'recipient_email', mode='before')
    @classmethod
    def clean_target_email(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        clean = str(v).strip().lower()
        return clean



class AuditEmailRequest(BaseModel):

    to_email: str

    clinician_name: Optional[str] = 'Active Clinician'

    export_format: Optional[str] = 'PDF'

    records_count: Optional[int] = 0

    time_scope: Optional[str] = 'All History'

    timestamp_utc: Optional[str] = None

    notary_hash: Optional[str] = 'SHA256-4f8b9e892c21ad8310c8ff0e34a7812bc88'

    download_url: Optional[str] = None

    filename: Optional[str] = None



    @field_validator('to_email')

    @classmethod

    def validate_to_email(cls, v: str) -> str:

        clean = v.strip().lower()

        if not EMAIL_REGEX.match(clean):

            raise ValueError('Invalid email address format.')

        return clean



class ScheduleAlertEmailRequest(BaseModel):
    to_email: str
    patient_name: str
    patient_mrn: Optional[str] = 'PT-NEW-001'
    clinician_name: Optional[str] = 'Authorized Clinician'
    check_number: Optional[str] = 'CHK-2026-CURRENT'
    schedule_date: Optional[str] = None
    course_end_date: Optional[str] = None
    regimen_duration: Optional[str] = '1 Month (30 Days)'
    medications: List[Dict[str, Any]] = []
    safety_alerts: List[Dict[str, Any]] = []
    notary_hash: Optional[str] = None
    portal_url: Optional[str] = 'https://prescription-dentalclinic.pages.dev/alerts'

    @field_validator('to_email')
    @classmethod
    def validate_to_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError('Invalid email address format.')
        return clean
