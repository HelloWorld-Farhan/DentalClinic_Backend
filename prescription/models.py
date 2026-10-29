import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, BigInteger, JSON
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    hashed_password = Column(String(255), nullable=True)
    auth_provider = Column(String(20), default="email")
    role = Column(String(30), default="USER")
    phone = Column(String(50), nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String(20), nullable=True)
    height = Column(String(20), nullable=True)
    weight = Column(String(20), nullable=True)
    has_allergies = Column(Boolean, default=False)
    allergies_description = Column(String(500), nullable=True)
    profile_completed = Column(Boolean, default=False)
    photo_url = Column(Text, nullable=True)
    is_google_linked = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_failed_attempt = Column(DateTime, nullable=True)
    remembered_device_id = Column(Text, nullable=True)
    two_factor_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class AuthOtp(Base):
    __tablename__ = "auth_otps"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), index=True, nullable=False)
    otp_code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), index=True, nullable=False)
    device_id = Column(String(255), index=True, nullable=False)
    device_name = Column(String(255), nullable=False)
    browser_os = Column(String(255), nullable=False)
    ip_address = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    status = Column(String(50), default="Success")
    is_active = Column(Boolean, default=True)
    details = Column(String(500), nullable=True)
    last_active = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class PrescriptionCheck(Base):
    __tablename__ = "prescription_checks"

    id = Column(String(64), primary_key=True)  # e.g. CHK-2026-4372
    user_email = Column(String(255), index=True, nullable=False)
    patient_id = Column(String(64), nullable=True)
    patient_name = Column(String(255), nullable=True)
    patient_mrn = Column(String(100), nullable=True)
    prescriptions = Column(JSON, nullable=True)  # List of prescribed items
    alerts = Column(JSON, nullable=True)         # List of drug interaction warnings
    highest_severity = Column(String(30), default="clear")
    reviewer_name = Column(String(120), nullable=True)
    status = Column(String(50), default="safe")
    pdf_filename = Column(String(255), nullable=True)
    pdf_url = Column(Text, nullable=True)
    word_url = Column(Text, nullable=True)
    csv_url = Column(Text, nullable=True)
    clinical_inquiries = Column(JSON, nullable=True)
    patient_vitals = Column(JSON, nullable=True)
    source_document_url = Column(Text, nullable=True)
    source_document_name = Column(String(255), nullable=True)
    source_type = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    digital_seal = Column(Text, nullable=True)
    timestamp_ms = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True)  # e.g. aud-17931...
    user_email = Column(String(255), index=True, nullable=False)
    action = Column(String(100), nullable=False)
    clinician_name = Column(String(120), nullable=True)
    patient_mrn = Column(String(100), nullable=True)
    event_details = Column(Text, nullable=True)
    severity = Column(String(30), default="SAFE")
    pdf_filename = Column(String(255), nullable=True)
    pdf_url = Column(Text, nullable=True)
    inner_data = Column(JSON, nullable=True)
    hash = Column(String(128), nullable=True)
    timestamp_ms = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    id = Column(String(64), primary_key=True)  # e.g. doc-17931...
    user_email = Column(String(255), index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=True)
    file_size = Column(Integer, default=0)
    storage_url = Column(Text, nullable=True)
    author_name = Column(String(120), nullable=True)
    extracted_rules_count = Column(Integer, default=0)
    status = Column(String(30), default="stored")
    uploaded_at = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ClinicalRule(Base):
    __tablename__ = "clinical_rules"

    id = Column(String(64), primary_key=True)  # e.g. rule-17931...
    user_email = Column(String(255), index=True, nullable=False)
    drug_a = Column(String(120), nullable=False)
    drug_b = Column(String(120), nullable=False)
    category = Column(String(80), nullable=True)
    severity = Column(String(30), default="moderate")
    mechanism = Column(Text, nullable=True)
    evidence = Column(String(80), default="Established")
    source_file = Column(String(255), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class PatientRecord(Base):
    __tablename__ = "patient_records"

    id = Column(String(64), primary_key=True)  # e.g. pt-17931...
    user_email = Column(String(255), index=True, nullable=False)
    mrn = Column(String(100), nullable=True)
    name = Column(String(120), nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(String(20), nullable=True)
    allergies = Column(JSON, nullable=True)
    conditions = Column(JSON, nullable=True)
    current_medications = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class UserCustomQuestion(Base):
    __tablename__ = "user_custom_questions"

    id = Column(String(64), primary_key=True)
    user_email = Column(String(255), index=True, nullable=False)
    question_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
