import os
import json
import base64
import urllib.request
import urllib.error
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/prescriptions", tags=["Prescription AI Extraction"])

# Model configuration
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
FALLBACK_MODELS = [DEFAULT_MODEL, "gemini-3.8-flash", "gemini-3.1-pro-preview"]

def get_active_keys() -> List[str]:
    """
    Collects all active Gemini keys from environment variables:
    1. GEMINI_API_KEYS (comma-separated list)
    2. GEMINI_KEY_1 ... GEMINI_KEY_15
    """
    keys = []
    comma_keys = os.getenv("GEMINI_API_KEYS", "")
    if comma_keys:
        for k in comma_keys.split(","):
            cleaned = k.strip()
            if cleaned and cleaned not in keys:
                keys.append(cleaned)

    for i in range(1, 16):
        k = os.getenv(f"GEMINI_KEY_{i}", "").strip()
        if k and k not in keys:
            keys.append(k)

    return keys

# Maintain an in-memory cursor for round-robin rotation across requests
_current_key_index = 0

def call_gemini_with_failover(prompt: str, inline_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Executes a Gemini generateContent call with automatic failover rotation.
    If a key hits a 429 rate limit or quota exhaustion, it immediately rotates
    to the next active key.
    """
    global _current_key_index
    keys = get_active_keys()
    if not keys:
        raise HTTPException(
            status_code=500,
            detail="No Gemini API keys configured. Please add GEMINI_API_KEYS to environment variables."
        )

    parts: List[Dict[str, Any]] = [{"text": prompt}]
    if inline_data:
        parts.append({"inlineData": inline_data})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    total_keys = len(keys)
    last_error = "Unknown error"

    # Try every active key in round-robin sequence
    for attempt in range(total_keys):
        key_idx = (_current_key_index + attempt) % total_keys
        api_key = keys[key_idx]

        for model_name in FALLBACK_MODELS:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            req = urllib.request.Request(
                endpoint,
                data=payload_bytes,
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as res:
                    res_body = json.loads(res.read().decode("utf-8"))
                    cand_text = (
                        res_body.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )
                    # Advance global index to load-balance keys across requests
                    _current_key_index = (key_idx + 1) % total_keys
                    return json.loads(cand_text)
            except urllib.error.HTTPError as e:
                err_text = e.read().decode("utf-8", errors="ignore")
                last_error = f"Key #{key_idx + 1} HTTP {e.code}: {err_text}"
                print(f"[Gemini Warning] Key #{key_idx + 1} ({model_name}) error: {e.code}. Attempting next...")
                # If 429 (rate limit) or 403/400 key error, break to next key
                if e.code in (429, 403, 400):
                    break
            except Exception as e:
                last_error = f"Key #{key_idx + 1} Exception: {str(e)}"
                print(f"[Gemini Warning] Key #{key_idx + 1} connection error: {e}. Rotating...")
                break

    raise HTTPException(
        status_code=502,
        detail=f"All {total_keys} Gemini API keys exhausted or rate-limited. Last error: {last_error}"
    )

@router.post("/extract")
async def extract_prescription(file: UploadFile = File(...)):
    """
    Extracts structured prescription data from uploaded PDFs, PNG, JPG, or WEBP images.
    Returns normalized patient metadata and individual medications.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    filename_lower = file.filename.lower()
    content_type = file.content_type or ""

    # Determine MIME type
    if filename_lower.endswith(".pdf") or "pdf" in content_type:
        mime_type = "application/pdf"
    elif filename_lower.endswith((".jpg", ".jpeg")) or "jpeg" in content_type:
        mime_type = "image/jpeg"
    elif filename_lower.endswith(".png") or "png" in content_type:
        mime_type = "image/png"
    elif filename_lower.endswith(".webp") or "webp" in content_type:
        mime_type = "image/webp"
    else:
        # Default binary fallback
        mime_type = "application/pdf" if b"%PDF" in content[:10] else "image/jpeg"

    b64_data = base64.b64encode(content).decode("utf-8")

    prompt = (
        "You are an expert clinical pharmacologist and medical document parser. "
        "Analyze this medical prescription or clinical document with utmost clinical precision. "
        "Extract doctor handwriting, abbreviations (e.g. TID, BID, PO, PRN, OD, HS, cap, tab, ℞), "
        "and normalize all dates to YYYY-MM-DD or standard readable formats.\n\n"
        "Generate relevant clinical decision support rules & contraindication safety warnings for the prescribed medications "
        "(e.g., drug-drug interactions, beta-lactam allergy contraindications, central nervous system depression warnings, "
        "or organ clearance titrations).\n\n"
        "Return ONLY a valid JSON object with EXACTLY this schema (do NOT wrap in markdown code blocks):\n"
        "{\n"
        '  "patient": {\n'
        '    "name": "string or null",\n'
        '    "age": number or null,\n'
        '    "gender": "Male | Female | Other | null",\n'
        '    "date": "YYYY-MM-DD or null",\n'
        '    "doctor": "string or null",\n'
        '    "diagnosis": "string or null",\n'
        '    "vitals": "string or null",\n'
        '    "address": "string or null"\n'
        '  },\n'
        '  "medicines": [\n'
        '    {\n'
        '      "drugName": "string",\n'
        '      "genericName": "string",\n'
        '      "dosage": "string (e.g. 500mg)",\n'
        '      "frequency": "string (e.g. Every 8 hours / TID)",\n'
        '      "duration": "string (e.g. 7 days)",\n'
        '      "route": "string (e.g. Oral (PO))",\n'
        '      "indication": "string"\n'
        '    }\n'
        '  ],\n'
        '  "rules": [\n'
        '    {\n'
        '      "drugA": "string",\n'
        '      "drugB": "string",\n'
        '      "severity": "contraindicated | major | moderate",\n'
        '      "category": "Drug-Drug | Drug-Allergy | Drug-Condition | Renal Dose Adjustment",\n'
        '      "description": "Clinical explanation of safety risk and mechanism",\n'
        '      "active": true\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    try:
        extracted = call_gemini_with_failover(
            prompt=prompt,
            inline_data={"mimeType": mime_type, "data": b64_data}
        )
        return {
            "status": "success",
            "filename": file.filename,
            "patient": extracted.get("patient", {}),
            "medicines": extracted.get("medicines", []),
            "rules": extracted.get("rules", [])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prescription extraction failed: {str(e)}")

@router.post("/extract-rules")
async def extract_clinical_rules(file: UploadFile = File(...)):
    """
    Extracts clinical decision support rules (drug interactions, contraindications)
    and any detected medicines from medical documents, pharmacology monographs,
    prescriptions, or guidelines.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    filename_lower = file.filename.lower()
    content_type = file.content_type or ""

    if filename_lower.endswith(".pdf") or "pdf" in content_type:
        mime_type = "application/pdf"
    elif filename_lower.endswith((".jpg", ".jpeg")):
        mime_type = "image/jpeg"
    elif filename_lower.endswith(".png"):
        mime_type = "image/png"
    elif filename_lower.endswith(".webp"):
        mime_type = "image/webp"
    else:
        mime_type = "application/pdf" if b"%PDF" in content[:10] else "image/jpeg"

    b64_data = base64.b64encode(content).decode("utf-8")

    prompt = (
        "You are an expert clinical pharmacologist. "
        "Analyze this document (which may be a prescription slip, clinical protocol, or pharmacology guide). "
        "Extract all prescribed medications, and extract/generate all drug-drug interactions, "
        "drug-allergy contraindications, and clinical dosing rules associated with them.\n\n"
        "Return ONLY a valid JSON object with this exact structure:\n"
        "{\n"
        '  "medicines": [\n'
        '    {\n'
        '      "drugName": "string",\n'
        '      "genericName": "string",\n'
        '      "dosage": "string",\n'
        '      "frequency": "string",\n'
        '      "duration": "string",\n'
        '      "route": "string",\n'
        '      "indication": "string"\n'
        '    }\n'
        '  ],\n'
        '  "rules": [\n'
        '    {\n'
        '      "drugA": "string",\n'
        '      "drugB": "string",\n'
        '      "severity": "contraindicated | major | moderate",\n'
        '      "category": "Drug-Drug | Drug-Allergy | Drug-Condition | Renal Dose Adjustment",\n'
        '      "description": "Clinical summary of interaction mechanism and consequence",\n'
        '      "active": true\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    try:
        extracted = call_gemini_with_failover(
            prompt=prompt,
            inline_data={"mimeType": mime_type, "data": b64_data}
        )
        return {
            "status": "success",
            "filename": file.filename,
            "medicines": extracted.get("medicines", []),
            "rules": extracted.get("rules", [])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rules extraction failed: {str(e)}")

