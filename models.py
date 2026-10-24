import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    hashed_password = Column(String(255), nullable=True)
    auth_provider = Column(String(20), default="email")
    role = Column(String(30), default="PHARMACIST")
    license_number = Column(String(50), nullable=True)
    clinic_id = Column(String(50), default="CLINIC_MAIN", nullable=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class PrescriptionAudit(Base):
    __tablename__ = "prescription_audits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clinic_id = Column(String(50), index=True, nullable=False)
    doctor_id = Column(String(50), nullable=False)
    patient_id = Column(String(50), nullable=False)
    drug_name = Column(String(120), nullable=False)
    dosage = Column(String(60), nullable=False)
    alert_level = Column(String(20), default="SAFE")
    risk_summary = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
