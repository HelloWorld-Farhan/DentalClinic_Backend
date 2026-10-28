from datetime import datetime, timezone
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import (
    PrescriptionCheck,
    AuditLog,
    UploadedDocument,
    ClinicalRule,
    PatientRecord,
)

router = APIRouter(prefix="/api/v1/sync", tags=["Cross-Device Sync"])

def clean_email(email: Optional[str]) -> str:
    if not email:
        raise HTTPException(status_code=400, detail="User email is required for sync operations")
    return email.strip().lower()

# ==========================================
# 1. UNIFIED FULL-STATE SYNC (PULL)
# ==========================================
@router.get("/all")
def get_all_user_data(
    email: str = Query(..., description="Clinician email address"),
    db: Session = Depends(get_db)
):
    """
    Retrieves all persistent cloud records for the authenticated clinician.
    Called when logging into any device to immediately hydrate client state.
    """
    norm_email = clean_email(email)

    checks = (
        db.query(PrescriptionCheck)
        .filter(PrescriptionCheck.user_email == norm_email)
        .order_by(PrescriptionCheck.created_at.desc())
        .limit(100)
        .all()
    )

    audit_logs = (
        db.query(AuditLog)
        .filter(AuditLog.user_email == norm_email)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )

    documents = (
        db.query(UploadedDocument)
        .filter(UploadedDocument.user_email == norm_email)
        .order_by(UploadedDocument.created_at.desc())
        .limit(100)
        .all()
    )

    rules = (
        db.query(ClinicalRule)
        .filter(ClinicalRule.user_email == norm_email)
        .order_by(ClinicalRule.created_at.desc())
        .all()
    )

    patients = (
        db.query(PatientRecord)
        .filter(PatientRecord.user_email == norm_email)
        .order_by(PatientRecord.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "email": norm_email,
        "checks": [
            {
                "id": c.id,
                "checkNumber": c.id,
                "patientId": c.patient_id,
                "patientName": c.patient_name,
                "patientMrn": c.patient_mrn,
                "prescriptions": c.prescriptions or [],
                "alerts": c.alerts or [],
                "highestSeverity": c.highest_severity,
                "reviewerName": c.reviewer_name,
                "status": c.status,
                "pdfFilename": c.pdf_filename,
                "pdfUrl": c.pdf_url,
                "notes": c.notes,
                "digitalSeal": c.digital_seal,
                "timestampMs": c.timestamp_ms,
                "createdAt": c.created_at.isoformat() if c.created_at else None,
            }
            for c in checks
        ],
        "auditLogs": [
            {
                "id": a.id,
                "action": a.action,
                "clinicianName": a.clinician_name,
                "patientMrn": a.patient_mrn,
                "eventDetails": a.event_details,
                "severity": a.severity,
                "pdfFilename": a.pdf_filename,
                "pdfUrl": a.pdf_url,
                "innerData": a.inner_data or {},
                "hash": a.hash,
                "timestampMs": a.timestamp_ms,
                "createdAt": a.created_at.isoformat() if a.created_at else None,
            }
            for a in audit_logs
        ],
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "fileType": d.file_type,
                "fileSize": d.file_size,
                "storageUrl": d.storage_url,
                "authorName": d.author_name,
                "extractedRulesCount": d.extracted_rules_count,
                "status": d.status,
                "uploadedAt": d.uploaded_at,
            }
            for d in documents
        ],
        "rules": [
            {
                "id": r.id,
                "drugA": r.drug_a,
                "drugB": r.drug_b,
                "category": r.category,
                "severity": r.severity,
                "mechanism": r.mechanism,
                "evidence": r.evidence,
                "sourceFile": r.source_file,
                "active": r.active,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rules
        ],
        "patients": [
            {
                "id": p.id,
                "mrn": p.mrn,
                "name": p.name,
                "age": p.age,
                "gender": p.gender,
                "allergies": p.allergies or [],
                "conditions": p.conditions or [],
                "currentMedications": p.current_medications or [],
            }
            for p in patients
        ],
    }

# ==========================================
# 2. BATCH PUSH / RECONCILIATION
# ==========================================
@router.post("/push")
def batch_push_user_data(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    norm_email = clean_email(payload.get("email"))

    # 1. Upsert checks
    checks_data = payload.get("checks", [])
    for c in checks_data:
        cid = str(c.get("id") or c.get("checkNumber") or "")
        if not cid:
            continue
        existing = db.query(PrescriptionCheck).filter(PrescriptionCheck.id == cid).first()
        if existing:
            existing.user_email = norm_email
            existing.prescriptions = c.get("prescriptions", [])
            existing.alerts = c.get("alerts", [])
            existing.highest_severity = c.get("highestSeverity") or c.get("severity") or existing.highest_severity
            existing.status = c.get("status") or existing.status
            existing.notes = c.get("notes") or existing.notes
            existing.pdf_filename = c.get("pdfFilename") or existing.pdf_filename
            existing.pdf_url = c.get("pdfUrl") or existing.pdf_url
        else:
            db.add(
                PrescriptionCheck(
                    id=cid,
                    user_email=norm_email,
                    patient_id=c.get("patientId"),
                    patient_name=c.get("patientName"),
                    patient_mrn=c.get("patientMrn") or c.get("patientId"),
                    prescriptions=c.get("prescriptions", []),
                    alerts=c.get("alerts", []),
                    highest_severity=c.get("highestSeverity") or c.get("severity") or "clear",
                    reviewer_name=c.get("reviewerName") or "Authorized Clinician",
                    status=c.get("status") or "safe",
                    pdf_filename=c.get("pdfFilename"),
                    pdf_url=c.get("pdfUrl"),
                    notes=c.get("notes"),
                    digital_seal=c.get("digitalSeal") or c.get("hash"),
                    timestamp_ms=c.get("timestampMs") or int(datetime.now(timezone.utc).timestamp() * 1000),
                )
            )

    # 2. Upsert audit logs
    audit_data = payload.get("auditLogs", [])
    for a in audit_data:
        aid = str(a.get("id") or "")
        if not aid:
            continue
        existing = db.query(AuditLog).filter(AuditLog.id == aid).first()
        if not existing:
            db.add(
                AuditLog(
                    id=aid,
                    user_email=norm_email,
                    action=a.get("action") or "Safety Screen Initiated",
                    clinician_name=a.get("clinicianName") or "Authorized Clinician",
                    patient_mrn=a.get("patientMrn") or "PT-GENERAL",
                    event_details=a.get("eventDetails") or "",
                    severity=a.get("severity") or "SAFE",
                    pdf_filename=a.get("pdfFilename"),
                    pdf_url=a.get("pdfUrl"),
                    inner_data=a.get("innerData") or {},
                    hash=a.get("hash"),
                    timestamp_ms=a.get("timestampMs") or int(datetime.now(timezone.utc).timestamp() * 1000),
                )
            )

    # 3. Upsert uploaded documents
    docs_data = payload.get("documents", [])
    for d in docs_data:
        did = str(d.get("id") or "")
        if not did:
            continue
        existing = db.query(UploadedDocument).filter(UploadedDocument.id == did).first()
        if not existing:
            db.add(
                UploadedDocument(
                    id=did,
                    user_email=norm_email,
                    filename=d.get("filename") or "Document",
                    file_type=d.get("fileType"),
                    file_size=d.get("fileSize") or 0,
                    storage_url=d.get("storageUrl"),
                    author_name=d.get("authorName") or "Authorized Clinician",
                    extracted_rules_count=d.get("extractedRulesCount") or 0,
                    status=d.get("status") or "stored",
                    uploaded_at=d.get("uploadedAt"),
                )
            )

    # 4. Upsert clinical rules
    rules_data = payload.get("rules", [])
    for r in rules_data:
        rid = str(r.get("id") or "")
        if not rid:
            continue
        existing = db.query(ClinicalRule).filter(ClinicalRule.id == rid).first()
        if existing:
            existing.active = bool(r.get("active", True))
            existing.severity = r.get("severity") or existing.severity
        else:
            db.add(
                ClinicalRule(
                    id=rid,
                    user_email=norm_email,
                    drug_a=r.get("drugA") or "",
                    drug_b=r.get("drugB") or "",
                    category=r.get("category") or "Clinical Alert",
                    severity=r.get("severity") or "moderate",
                    mechanism=r.get("mechanism") or "",
                    evidence=r.get("evidence") or "Established",
                    source_file=r.get("sourceFile"),
                    active=bool(r.get("active", True)),
                )
            )

    # 5. Upsert patients
    patients_data = payload.get("patients", [])
    for p in patients_data:
        pid = str(p.get("id") or "")
        if not pid:
            continue
        existing = db.query(PatientRecord).filter(PatientRecord.id == pid).first()
        if existing:
            existing.name = p.get("name") or existing.name
            existing.age = p.get("age") or existing.age
            existing.allergies = p.get("allergies") or existing.allergies
            existing.conditions = p.get("conditions") or existing.conditions
            existing.current_medications = p.get("currentMedications") or existing.current_medications
        else:
            db.add(
                PatientRecord(
                    id=pid,
                    user_email=norm_email,
                    mrn=p.get("mrn") or pid,
                    name=p.get("name") or "Patient",
                    age=p.get("age"),
                    gender=p.get("gender"),
                    allergies=p.get("allergies") or [],
                    conditions=p.get("conditions") or [],
                    current_medications=p.get("currentMedications") or [],
                )
            )

    db.commit()
    return {"status": "success", "message": "Batch synced successfully to Supabase cloud"}

# ==========================================
# 3. GRANULAR REAL-TIME ACTIONS
# ==========================================
@router.post("/check")
def save_single_check(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    norm_email = clean_email(payload.get("email"))
    c = payload.get("check") or payload
    cid = str(c.get("id") or c.get("checkNumber") or "")
    if not cid:
        raise HTTPException(status_code=400, detail="Check ID is required")

    existing = db.query(PrescriptionCheck).filter(PrescriptionCheck.id == cid).first()
    if existing:
        existing.user_email = norm_email
        existing.prescriptions = c.get("prescriptions", [])
        existing.alerts = c.get("alerts", [])
        existing.highest_severity = c.get("highestSeverity") or c.get("severity") or existing.highest_severity
        existing.status = c.get("status") or existing.status
        existing.notes = c.get("notes") or existing.notes
        existing.pdf_filename = c.get("pdfFilename") or existing.pdf_filename
        existing.pdf_url = c.get("pdfUrl") or existing.pdf_url
    else:
        existing = PrescriptionCheck(
            id=cid,
            user_email=norm_email,
            patient_id=c.get("patientId"),
            patient_name=c.get("patientName"),
            patient_mrn=c.get("patientMrn") or c.get("patientId"),
            prescriptions=c.get("prescriptions", []),
            alerts=c.get("alerts", []),
            highest_severity=c.get("highestSeverity") or c.get("severity") or "clear",
            reviewer_name=c.get("reviewerName") or "Authorized Clinician",
            status=c.get("status") or "safe",
            pdf_filename=c.get("pdfFilename"),
            pdf_url=c.get("pdfUrl"),
            notes=c.get("notes"),
            digital_seal=c.get("digitalSeal") or c.get("hash"),
            timestamp_ms=c.get("timestampMs") or int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        db.add(existing)

    db.commit()
    return {"status": "success", "id": cid}

@router.post("/audit-log")
def save_single_audit_log(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    norm_email = clean_email(payload.get("email"))
    a = payload.get("auditLog") or payload
    aid = str(a.get("id") or "")
    if not aid:
        raise HTTPException(status_code=400, detail="Audit log ID is required")

    existing = db.query(AuditLog).filter(AuditLog.id == aid).first()
    if not existing:
        db.add(
            AuditLog(
                id=aid,
                user_email=norm_email,
                action=a.get("action") or "Safety Screen Initiated",
                clinician_name=a.get("clinicianName") or "Authorized Clinician",
                patient_mrn=a.get("patientMrn") or "PT-GENERAL",
                event_details=a.get("eventDetails") or "",
                severity=a.get("severity") or "SAFE",
                pdf_filename=a.get("pdfFilename"),
                pdf_url=a.get("pdfUrl"),
                inner_data=a.get("innerData") or {},
                hash=a.get("hash"),
                timestamp_ms=a.get("timestampMs") or int(datetime.now(timezone.utc).timestamp() * 1000),
            )
        )
        db.commit()

    return {"status": "success", "id": aid}

@router.post("/document")
def save_single_document(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    norm_email = clean_email(payload.get("email"))
    d = payload.get("document") or payload
    did = str(d.get("id") or "")
    if not did:
        raise HTTPException(status_code=400, detail="Document ID is required")

    existing = db.query(UploadedDocument).filter(UploadedDocument.id == did).first()
    if not existing:
        db.add(
            UploadedDocument(
                id=did,
                user_email=norm_email,
                filename=d.get("filename") or "Document",
                file_type=d.get("fileType"),
                file_size=d.get("fileSize") or 0,
                storage_url=d.get("storageUrl"),
                author_name=d.get("authorName") or "Authorized Clinician",
                extracted_rules_count=d.get("extractedRulesCount") or 0,
                status=d.get("status") or "stored",
                uploaded_at=d.get("uploadedAt"),
            )
        )
        db.commit()

    return {"status": "success", "id": did}

@router.delete("/document/{doc_id}")
def delete_single_document(
    doc_id: str,
    email: str = Query(...),
    db: Session = Depends(get_db)
):
    norm_email = clean_email(email)
    doc = db.query(UploadedDocument).filter(UploadedDocument.id == doc_id, UploadedDocument.user_email == norm_email).first()
    if doc:
        db.delete(doc)
        db.commit()
    return {"status": "success", "deletedId": doc_id}

@router.post("/rule")
def save_single_rule(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    norm_email = clean_email(payload.get("email"))
    r = payload.get("rule") or payload
    rid = str(r.get("id") or "")
    if not rid:
        raise HTTPException(status_code=400, detail="Rule ID is required")

    existing = db.query(ClinicalRule).filter(ClinicalRule.id == rid).first()
    if existing:
        existing.active = bool(r.get("active", True))
        existing.severity = r.get("severity") or existing.severity
        existing.mechanism = r.get("mechanism") or existing.mechanism
    else:
        db.add(
            ClinicalRule(
                id=rid,
                user_email=norm_email,
                drug_a=r.get("drugA") or "",
                drug_b=r.get("drugB") or "",
                category=r.get("category") or "Clinical Alert",
                severity=r.get("severity") or "moderate",
                mechanism=r.get("mechanism") or "",
                evidence=r.get("evidence") or "Established",
                source_file=r.get("sourceFile"),
                active=bool(r.get("active", True)),
            )
        )
    db.commit()
    return {"status": "success", "id": rid}

@router.delete("/rule/{rule_id}")
def delete_single_rule(
    rule_id: str,
    email: str = Query(...),
    db: Session = Depends(get_db)
):
    norm_email = clean_email(email)
    rule = db.query(ClinicalRule).filter(ClinicalRule.id == rule_id, ClinicalRule.user_email == norm_email).first()
    if rule:
        db.delete(rule)
        db.commit()
    return {"status": "success", "deletedId": rule_id}

@router.patch("/rule/{rule_id}/toggle")
def toggle_single_rule(
    rule_id: str,
    email: str = Query(...),
    db: Session = Depends(get_db)
):
    norm_email = clean_email(email)
    rule = db.query(ClinicalRule).filter(ClinicalRule.id == rule_id, ClinicalRule.user_email == norm_email).first()
    if rule:
        rule.active = not rule.active
        db.commit()
        return {"status": "success", "id": rule_id, "active": rule.active}
    return {"status": "not_found", "id": rule_id}

@router.delete("/rules-by-source")
def delete_rules_by_source(
    source: str = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db)
):
    norm_email = clean_email(email)
    rules = db.query(ClinicalRule).filter(ClinicalRule.user_email == norm_email).all()
    deleted_count = 0
    for r in rules:
        if r.source_file and (r.source_file == source or source in r.source_file or r.source_file in source):
            db.delete(r)
            deleted_count += 1
    db.commit()
    return {"status": "success", "deletedCount": deleted_count}
