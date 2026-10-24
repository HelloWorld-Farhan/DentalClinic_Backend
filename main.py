import os
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt

from database import engine, get_db, Base
import models

# Automatically initialize tables in connected PostgreSQL database
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Database init notice: {e}")

app = FastAPI(
    title="Smile Clinic Core API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Multi-Origin configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://prescription-dentalclinic.pages.dev",
        "https://*.pages.dev",
        "https://prescription.propnexai.com",
        "https://propnexai.com",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("JWT_SECRET", "smile_clinic_jwt_secure_secret_token_2026")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ----------------- Schemas -----------------
class HealthCheck(BaseModel):
    status: str
    service: str
    timestamp: datetime

class UserRegister(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    license_number: Optional[str] = None
    clinic_id: Optional[str] = "CLINIC_MAIN"
    role: Optional[str] = "PHARMACIST"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class DrugCheckRequest(BaseModel):
    patient_id: str
    patient_name: str
    doctor_id: str
    allergies: List[str] = []
    current_medications: List[str] = []
    prescribed_drug: str
    dosage: str

class DrugCheckResponse(BaseModel):
    alert_level: str
    message: str
    risk_summary: str
    timestamp: datetime

# ----------------- Root & Health (UptimeRobot / Render) -----------------
@app.get("/", response_model=HealthCheck)
@app.get("/health", response_model=HealthCheck)
def health_check():
    """Liveness probe used by UptimeRobot & Render to prevent cold starts."""
    return HealthCheck(
        status="healthy",
        service="SmileClinic-CoreAPI",
        timestamp=datetime.utcnow()
    )

# ----------------- Auth Endpoints -----------------
@app.post("/api/v1/auth/register", response_model=TokenResponse)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email is already registered")

    new_user = models.User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=pwd_context.hash(user_in.password),
        license_number=user_in.license_number,
        clinic_id=user_in.clinic_id or "CLINIC_MAIN",
        role=user_in.role or "PHARMACIST",
        auth_provider="email"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = jwt.encode(
        {"sub": new_user.email, "role": new_user.role, "exp": datetime.utcnow() + timedelta(days=7)},
        SECRET_KEY,
        algorithm=ALGORITHM
    )
    return TokenResponse(
        access_token=token,
        user={"id": new_user.id, "email": new_user.email, "full_name": new_user.full_name, "role": new_user.role}
    )

@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(creds: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == creds.email).first()
    if not user or not user.hashed_password or not pwd_context.verify(creds.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = jwt.encode(
        {"sub": user.email, "role": user.role, "exp": datetime.utcnow() + timedelta(days=7)},
        SECRET_KEY,
        algorithm=ALGORITHM
    )
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}
    )

# ----------------- Prescription CDS Screening -----------------
@app.post("/api/v1/prescriptions/check", response_model=DrugCheckResponse)
def check_prescription(req: DrugCheckRequest, db: Session = Depends(get_db)):
    prescribed = req.prescribed_drug.strip().lower()
    alert_level = "SAFE"
    summary = "No adverse drug interactions or allergy contraindications detected."

    # Allergy screening
    for allergy in req.allergies:
        if allergy.lower() in prescribed or prescribed in allergy.lower():
            alert_level = "CRITICAL"
            summary = f"Contraindicated: Patient allergy alert for '{allergy}'."
            break

    # Pharmacological drug-drug rules
    if alert_level == "SAFE":
        curr_meds_lower = [m.lower() for m in req.current_medications]
        if "amoxicillin" in prescribed and any("methotrexate" in m for m in curr_meds_lower):
            alert_level = "CRITICAL"
            summary = "Amoxicillin reduces renal clearance of Methotrexate, causing severe bone marrow toxicity."
        elif "ibuprofen" in prescribed and any("warfarin" in m or "aspirin" in m for m in curr_meds_lower):
            alert_level = "WARNING"
            summary = "NSAID combined with anticoagulant significantly increases gastrointestinal bleeding risk."
        elif "erythromycin" in prescribed and any("theophylline" in m for m in curr_meds_lower):
            alert_level = "WARNING"
            summary = "Erythromycin increases theophylline plasma concentration."

    # Audit log entry
    audit = models.PrescriptionAudit(
        clinic_id="CLINIC_MAIN",
        doctor_id=req.doctor_id,
        patient_id=req.patient_id,
        drug_name=req.prescribed_drug,
        dosage=req.dosage,
        alert_level=alert_level,
        risk_summary=summary
    )
    db.add(audit)
    db.commit()

    return DrugCheckResponse(
        alert_level=alert_level,
        message="Safety screening evaluation complete.",
        risk_summary=summary,
        timestamp=datetime.utcnow()
    )

@app.get("/api/v1/prescriptions/audit")
def get_audit_trail(db: Session = Depends(get_db)):
    return db.query(models.PrescriptionAudit).order_by(models.PrescriptionAudit.timestamp.desc()).limit(50).all()
