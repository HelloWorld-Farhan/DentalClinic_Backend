import os
import csv
import json
import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from .models import (
    PrescriptionCheck,
    AuditLog,
    UploadedDocument,
    PatientRecord,
    ClinicalRule,
    UserNotificationState,
)
from dotenv import load_dotenv

load_dotenv()

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID") or "f0aefe721667f2055f6a14b864d43a1d"
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID") or "66d85be1930c9b362b831234b0efdc74"
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY") or "d1ce125bffd95f46205a9cb09a5cc55bc256815b4aef10221e39aca6f0fdc715"
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME") or "dental-clinic-records"
R2_PUBLIC_URL = (os.getenv("R2_PUBLIC_URL") or "https://pub-e6b50314f766405596ea974a88ed73cd.r2.dev").rstrip("/")

def get_r2_client():
    account_id = os.getenv("R2_ACCOUNT_ID") or R2_ACCOUNT_ID
    access_key = os.getenv("R2_ACCESS_KEY_ID") or R2_ACCESS_KEY_ID
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY") or R2_SECRET_ACCESS_KEY
    bucket = os.getenv("R2_BUCKET_NAME") or R2_BUCKET_NAME
    if not (account_id and access_key and secret_key):
        return None
    try:
        import boto3
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto"
        )
        endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto"
        )
    except Exception as e:
        print(f"[R2 Sync Warning] Boto3 init error: {e}")
        return None

def parse_report_csv_content(csv_text: str):
    lines = [l.strip() for l in csv_text.strip().splitlines() if l.strip()]
    header_data = {}
    meds = []
    alerts = []
    current_section = "header"

    for line in lines:
        if line.startswith('\ufeff'):
            line = line[1:]
        try:
            parts = [p.strip() for p in next(csv.reader([line]))]
        except Exception:
            continue
        if not parts or not any(parts):
            continue

        first = parts[0]
        if first in ["Check ID", "Patient Name", "Patient MRN", "Overall Status", "Digital Seal"]:
            header_data[first] = parts[1] if len(parts) > 1 else ""
        elif first == "Drug Name":
            current_section = "meds"
        elif first == "Severity":
            current_section = "alerts"
        elif current_section == "meds":
            meds.append({
                "drugName": parts[0] if len(parts) > 0 else "",
                "genericName": parts[1] if len(parts) > 1 else "",
                "dosage": parts[2] if len(parts) > 2 else "",
                "route": parts[3] if len(parts) > 3 else "",
                "frequency": parts[4] if len(parts) > 4 else "",
                "duration": parts[5] if len(parts) > 5 else "",
                "safetyStatus": parts[6] if len(parts) > 6 else "Safe to Dispense",
                "clinicalIndication": parts[7] if len(parts) > 7 else ""
            })
        elif current_section == "alerts":
            sev = (parts[0] if len(parts) > 0 else "moderate").lower()
            drug_a = parts[1] if len(parts) > 1 else ""
            drug_b = parts[2] if len(parts) > 2 else ""
            interacting = [drug_a, drug_b] if drug_a and drug_b else []
            alerts.append({
                "id": f"alt-{abs(hash(drug_a + drug_b + sev)) % 1000000}",
                "severity": sev,
                "drugA": drug_a,
                "drugB": drug_b,
                "interactingDrugs": interacting,
                "category": parts[3] if len(parts) > 3 else "Drug-Drug",
                "description": parts[4] if len(parts) > 4 else "",
                "clinicalRecommendation": parts[4] if len(parts) > 4 else "",
                "action": "Clinical Review Advised"
            })

    return header_data, meds, alerts

def sync_db_state_to_r2(email: str, db: Session) -> bool:
    """Exports current database clinical records for the user and uploads to R2 as clinical_sync_data.json."""
    norm_email = email.strip().lower()
    s3 = get_r2_client()
    if not s3:
        return False

    try:
        checks = db.query(PrescriptionCheck).filter(PrescriptionCheck.user_email == norm_email).all()
        audit_logs = db.query(AuditLog).filter(AuditLog.user_email == norm_email).all()
        documents = db.query(UploadedDocument).filter(UploadedDocument.user_email == norm_email).all()
        patients = db.query(PatientRecord).filter(PatientRecord.user_email == norm_email).all()
        rules = db.query(ClinicalRule).filter(ClinicalRule.user_email == norm_email).all()

        sync_payload = {
            "version": "1.0",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
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
                    "wordUrl": c.word_url,
                    "csvUrl": c.csv_url,
                    "clinicalInquiries": c.clinical_inquiries or [],
                    "patientVitals": c.patient_vitals or {},
                    "sourceDocumentUrl": c.source_document_url,
                    "sourceDocumentName": c.source_document_name,
                    "sourceType": c.source_type,
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
                }
                for r in rules
            ]
        }

        key = f"users/{norm_email}/clinical_sync_data.json"
        s3.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=json.dumps(sync_payload, indent=2).encode("utf-8"),
            ContentType="application/json"
        )
        print(f"[R2 Sync] Successfully mirrored {len(checks)} checks and {len(audit_logs)} logs to {key}")
        return True
    except Exception as e:
        print(f"[R2 Sync Error] Failed to mirror DB state to R2: {e}")
        return False

def reconcile_user_data_from_r2(email: str, db: Session) -> dict:
    """
    Reconciles all historical data for the user from Cloudflare R2 into SQLite.
    1. Checks for users/{email}/clinical_sync_data.json
    2. Scans users/{email}/report/csv/ and users/{email}/prescription/pdf/ to recover full checks & documents
    3. Populates SQLite and commits
    4. Mirrored back to clinical_sync_data.json
    """
    norm_email = email.strip().lower()
    s3 = get_r2_client()
    if not s3:
        print("[R2 Sync Warning] No R2 client available for reconciliation")
        return {"checks": 0, "documents": 0, "auditLogs": 0}

    print(f"[R2 Sync] Starting reconciliation for {norm_email}...")
    recovered_checks = 0
    recovered_docs = 0
    recovered_audits = 0

    # 1. Try reading master backup clinical_sync_data.json first
    sync_key = f"users/{norm_email}/clinical_sync_data.json"
    backup_data = None
    try:
        obj = s3.get_object(Bucket=R2_BUCKET_NAME, Key=sync_key)
        backup_data = json.loads(obj["Body"].read().decode("utf-8"))
        print(f"[R2 Sync] Found existing master backup in R2 with {len(backup_data.get('checks', []))} checks")
    except Exception:
        pass

    seen_check_ids = set(c.id for c in db.query(PrescriptionCheck.id).filter(PrescriptionCheck.user_email == norm_email).all())
    seen_audit_ids = set(a.id for a in db.query(AuditLog.id).filter(AuditLog.user_email == norm_email).all())
    seen_doc_ids = set(d.id for d in db.query(UploadedDocument.id).filter(UploadedDocument.user_email == norm_email).all())

    if backup_data and isinstance(backup_data.get("checks"), list) and len(backup_data["checks"]) > 0:
        for c in backup_data["checks"]:
            cid = c.get("id") or c.get("checkNumber")
            if not cid or cid in seen_check_ids:
                continue
            db.add(
                PrescriptionCheck(
                    id=cid,
                    user_email=norm_email,
                    patient_id=c.get("patientId"),
                    patient_name=c.get("patientName"),
                    patient_mrn=c.get("patientMrn"),
                    prescriptions=c.get("prescriptions", []),
                    alerts=c.get("alerts", []),
                    highest_severity=c.get("highestSeverity") or "clear",
                    reviewer_name=c.get("reviewerName") or "Dr. Farhan Khalid, MD",
                    status=c.get("status") or "safe",
                    pdf_filename=c.get("pdfFilename"),
                    pdf_url=c.get("pdfUrl"),
                    word_url=c.get("wordUrl"),
                    csv_url=c.get("csvUrl"),
                    clinical_inquiries=c.get("clinicalInquiries", []),
                    patient_vitals=c.get("patientVitals", {}),
                    source_document_url=c.get("sourceDocumentUrl"),
                    source_document_name=c.get("sourceDocumentName"),
                    source_type=c.get("sourceType"),
                    notes=c.get("notes"),
                    digital_seal=c.get("digitalSeal"),
                    timestamp_ms=c.get("timestampMs") or int(datetime.now(timezone.utc).timestamp() * 1000),
                )
            )
            seen_check_ids.add(cid)
            recovered_checks += 1

        for a in backup_data.get("auditLogs", []):
            aid = a.get("id")
            if not aid or aid in seen_audit_ids:
                continue
            db.add(
                AuditLog(
                    id=aid,
                    user_email=norm_email,
                    action=a.get("action") or "Safety Screen Executed",
                    clinician_name=a.get("clinicianName") or "Dr. Farhan Khalid, MD",
                    patient_mrn=a.get("patientMrn") or "PT-NEW-001",
                    event_details=a.get("eventDetails") or "",
                    severity=a.get("severity") or "SAFE",
                    pdf_filename=a.get("pdfFilename"),
                    pdf_url=a.get("pdfUrl"),
                    inner_data=a.get("innerData") or {},
                    hash=a.get("hash"),
                    timestamp_ms=a.get("timestampMs") or int(datetime.now(timezone.utc).timestamp() * 1000),
                )
            )
            seen_audit_ids.add(aid)
            recovered_audits += 1

        for d in backup_data.get("documents", []):
            did = d.get("id")
            if not did or did in seen_doc_ids:
                continue
            db.add(
                UploadedDocument(
                    id=did,
                    user_email=norm_email,
                    filename=d.get("filename") or "Document.pdf",
                    file_type=d.get("fileType") or "application/pdf",
                    file_size=d.get("fileSize") or 0,
                    storage_url=d.get("storageUrl"),
                    author_name=d.get("authorName") or "Dr. Farhan Khalid, MD",
                    extracted_rules_count=d.get("extractedRulesCount") or 0,
                    status=d.get("status") or "stored",
                    uploaded_at=d.get("uploadedAt"),
                )
            )
            seen_doc_ids.add(did)
            recovered_docs += 1

    # 2. List all R2 objects for user to discover report CSVs, report PDFs, Word documents and prescription PDFs
    try:
        paginator = s3.get_paginator("list_objects_v2")
        prefix = f"users/{norm_email}/"
        user_objects = []
        for page in paginator.paginate(Bucket=R2_BUCKET_NAME, Prefix=prefix):
            user_objects.extend(page.get("Contents", []))

        # Index PDFs and Word files by check ID or timestamp
        pdf_map = {}
        word_map = {}
        for obj in user_objects:
            k = obj["Key"]
            m_chk = re.search(r'(CHK-\d{4}-\d+|chk-\d+)', k, re.I)
            chk_key = m_chk.group(1).upper() if m_chk else None
            m_ts = re.search(r'/(\d{13})_', k)
            ts_key = m_ts.group(1) if m_ts else None

            if k.endswith(".pdf") and "/report/" in k:
                if chk_key:
                    pdf_map[chk_key] = f"{R2_PUBLIC_URL}/{k}"
                if ts_key:
                    pdf_map[ts_key] = f"{R2_PUBLIC_URL}/{k}"
            elif k.endswith(".docx") and "/report/" in k:
                if chk_key:
                    word_map[chk_key] = f"{R2_PUBLIC_URL}/{k}"
                if ts_key:
                    word_map[ts_key] = f"{R2_PUBLIC_URL}/{k}"

        # 3. Parse report CSVs
        for obj in user_objects:
            k = obj["Key"]
            if not (k.endswith(".csv") and "/report/" in k):
                continue

            m_ts = re.search(r'/(\d{13})_', k)
            ts_ms = int(m_ts.group(1)) if m_ts else int(obj["LastModified"].timestamp() * 1000)

            try:
                csv_resp = s3.get_object(Bucket=R2_BUCKET_NAME, Key=k)
                csv_text = csv_resp["Body"].read().decode("utf-8")
                h, meds, alerts = parse_report_csv_content(csv_text)
            except Exception as e:
                print(f"[R2 Sync Warning] Error reading CSV {k}: {e}")
                continue

            cid = h.get("Check ID")
            if not cid:
                m_chk = re.search(r'(CHK-\d{4}-\d+|chk-\d+)', k, re.I)
                cid = m_chk.group(1).upper() if m_chk else f"CHK-{ts_ms}"

            patient_name = h.get("Patient Name") or "Farhan Khalid"
            patient_mrn = h.get("Patient MRN") or "PT-NEW-001"
            status_text = h.get("Overall Status") or "Safe to Dispense"
            digital_seal = h.get("Digital Seal")

            # Determine highest severity
            severities = [a.get("severity", "").lower() for a in alerts]
            if "contraindicated" in severities:
                highest_sev = "contraindicated"
            elif "major" in severities:
                highest_sev = "major"
            elif "moderate" in severities:
                highest_sev = "moderate"
            elif "minor" in severities:
                highest_sev = "minor"
            else:
                highest_sev = "clear"

            pdf_url = pdf_map.get(cid) or pdf_map.get(str(ts_ms))
            word_url = word_map.get(cid) or word_map.get(str(ts_ms))
            csv_url = f"{R2_PUBLIC_URL}/{k}"

            # Check if exists in DB or seen
            if cid not in seen_check_ids and not db.query(PrescriptionCheck).filter(PrescriptionCheck.id == cid).first():
                new_chk = PrescriptionCheck(
                    id=cid,
                    user_email=norm_email,
                    patient_id=patient_mrn,
                    patient_name=patient_name,
                    patient_mrn=patient_mrn,
                    prescriptions=meds,
                    alerts=alerts,
                    highest_severity=highest_sev,
                    reviewer_name="Dr. Farhan Khalid, MD",
                    status=status_text,
                    pdf_filename=f"{cid}_CDS_Report.pdf",
                    pdf_url=pdf_url,
                    word_url=word_url,
                    csv_url=csv_url,
                    clinical_inquiries=[],
                    patient_vitals={"age": 28, "gender": "Male", "weight": "72 kg"},
                    source_document_url=None,
                    source_document_name="Prescription Document",
                    source_type="application/pdf",
                    notes="Reconciled from Cloudflare R2 clinical archive.",
                    digital_seal=digital_seal,
                    timestamp_ms=ts_ms,
                    created_at=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
                )
                db.add(new_chk)
                seen_check_ids.add(cid)
                recovered_checks += 1

                # Add matching Audit Log
                audit_id = f"aud-{ts_ms}"
                if audit_id not in seen_audit_ids and not db.query(AuditLog).filter(AuditLog.id == audit_id).first():
                    sev_label = highest_sev.upper() if highest_sev != "clear" else "SAFE"
                    db.add(
                        AuditLog(
                            id=audit_id,
                            user_email=norm_email,
                            action="Safety Screen Executed",
                            clinician_name="Dr. Farhan Khalid, MD",
                            patient_mrn=patient_mrn,
                            event_details=f"Clinical drug regimen screened for {patient_name} ({patient_mrn}). {len(meds)} prescribed items, {len(alerts)} alerts. Status: {status_text}.",
                            severity=sev_label,
                            pdf_filename=f"{cid}_CDS_Report.pdf",
                            pdf_url=pdf_url,
                            inner_data={
                                "checkId": cid,
                                "patientName": patient_name,
                                "patientMrn": patient_mrn,
                                "highestSeverity": highest_sev,
                                "medCount": len(meds),
                                "alertCount": len(alerts),
                            },
                            hash=digital_seal,
                            timestamp_ms=ts_ms,
                            created_at=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
                        )
                    )
                    seen_audit_ids.add(audit_id)
                    recovered_audits += 1

        # 4. Recover prescription PDFs as UploadedDocuments
        for obj in user_objects:
            k = obj["Key"]
            if not (k.endswith(".pdf") and "/prescription/" in k):
                continue
            filename = k.rsplit("/", 1)[-1]
            # Strip timestamp prefix for display
            clean_name = re.sub(r'^\d{13}_', '', filename)
            doc_id = f"doc-{re.sub(r'[^a-zA-Z0-9]', '', filename)[:32]}"
            doc_url = f"{R2_PUBLIC_URL}/{k}"
            ts_ms = int(obj["LastModified"].timestamp() * 1000)

            if doc_id not in seen_doc_ids and not db.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first():
                db.add(
                    UploadedDocument(
                        id=doc_id,
                        user_email=norm_email,
                        filename=clean_name,
                        file_type="application/pdf",
                        file_size=obj["Size"],
                        storage_url=doc_url,
                        author_name="Dr. Farhan Khalid, MD",
                        extracted_rules_count=len(alerts) if alerts else 3,
                        status="analyzed",
                        uploaded_at=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat(),
                        created_at=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
                    )
                )
                seen_doc_ids.add(doc_id)
                recovered_docs += 1

        # 5. Ensure Patient Record for Farhan Khalid
        existing_patient = db.query(PatientRecord).filter(PatientRecord.user_email == norm_email, PatientRecord.mrn == "PT-NEW-001").first()
        if not existing_patient:
            db.add(
                PatientRecord(
                    id="pt-new-001",
                    user_email=norm_email,
                    mrn="PT-NEW-001",
                    name="Farhan Khalid",
                    age=28,
                    gender="Male",
                    allergies=["Penicillin"],
                    conditions=["Hypertension", "Dental Sensitivity"],
                    current_medications=["Rosuvastatin", "Pantoprazole"],
                )
            )

        db.commit()
        print(f"[R2 Sync] Reconciliation committed: +{recovered_checks} checks, +{recovered_docs} docs, +{recovered_audits} audits.")

        # 6. Upload updated clinical_sync_data.json to Cloudflare R2
        sync_db_state_to_r2(norm_email, db)

    except Exception as e:
        print(f"[R2 Sync Error] Reconciliation exception: {e}")
        db.rollback()

    return {
        "recoveredChecks": recovered_checks,
        "recoveredDocs": recovered_docs,
        "recoveredAudits": recovered_audits,
    }
