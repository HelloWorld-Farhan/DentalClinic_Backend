import os
import json
import base64
import zipfile
import io
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
from typing import List, Optional, Dict, Any, Tuple
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter(prefix="/api/prescriptions", tags=["Prescription AI Extraction"])

# Model configuration - Prioritize ultra-fast Gemini 3.5 Flash Lite with 2.5 Flash fallback
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODELS = [DEFAULT_MODEL, "gemini-2.5-flash"]

def get_active_keys() -> List[str]:
    """Collects all active Gemini keys from environment variables."""
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

_current_key_index = 0

def call_gemini_with_failover(prompt: str, inline_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Executes a Gemini generateContent call with automatic 14-key failover rotation."""
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

    for attempt in range(min(3, total_keys)):
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
                with urllib.request.urlopen(req, timeout=16) as res:
                    res_body = json.loads(res.read().decode("utf-8"))
                    cand_text = (
                        res_body.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )
                    _current_key_index = (key_idx + 1) % total_keys
                    return json.loads(cand_text)
            except urllib.error.HTTPError as e:
                err_text = e.read().decode("utf-8", errors="ignore")
                last_error = f"Key #{key_idx + 1} HTTP {e.code}: {err_text}"
                print(f"[Gemini Warning] Key #{key_idx + 1} ({model_name}) error: {e.code}. Rotating...")
                if e.code in (429, 403, 400):
                    break
            except Exception as e:
                last_error = f"Key #{key_idx + 1} Exception: {str(e)}"
                print(f"[Gemini Warning] Key #{key_idx + 1} error: {e}. Rotating...")
                break

    raise HTTPException(
        status_code=502,
        detail=f"All {total_keys} Gemini API keys exhausted or rate-limited. Last error: {last_error}"
    )

def extract_docx_content(content: bytes) -> Tuple[str, Optional[Tuple[str, str]]]:
    """
    Extracts text from Word DOCX XML, and checks for any embedded scanned prescription images.
    Returns (extracted_text, (mime_type, base64_image_data) | None).
    """
    texts = []
    embedded_media = None
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if "word/document.xml" in z.namelist():
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                nodes = [node.text for node in tree.iter() if node.text]
                if nodes:
                    texts.append("\n".join(nodes))

            # Look for embedded prescription slip scans
            for name in z.namelist():
                if name.startswith("word/media/") and name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    img_bytes = z.read(name)
                    mime = "image/png" if name.lower().endswith(".png") else "image/jpeg"
                    embedded_media = (mime, base64.b64encode(img_bytes).decode("utf-8"))
                    break
    except Exception as e:
        print(f"[DOCX Parse Warning] {e}")

    return "\n".join(texts), embedded_media

def decode_text_content(content: bytes) -> str:
    """Decodes plain text or CSV data across common clinical encodings."""
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")

def extract_pdf_content(content: bytes) -> Tuple[Optional[Dict[str, str]], str]:
    """
    Intelligently extracts text or rendered images from PDF files.
    Tries PyMuPDF (fitz) or pypdf to extract clean text. If text is sparse (scanned document),
    extracts embedded page images or renders page 1 to JPEG.
    """
    extracted_text = ""
    inline_data = None

    # Step 1: Try PyMuPDF (fitz)
    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        for page in doc:
            extracted_text += page.get_text() + "\n"
        
        if len(extracted_text.strip()) > 20:
            return None, f"\n[Extracted Digital PDF Prescription Text]:\n{extracted_text.strip()}"

        if len(doc) > 0:
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("jpeg")
            inline_data = {
                "mimeType": "image/jpeg",
                "data": base64.b64encode(img_bytes).decode("utf-8")
            }
            return inline_data, extracted_text.strip()
    except Exception as e:
        print(f"[PyMuPDF Warning] {e}")

    # Step 2: Fallback to pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        for p in reader.pages:
            extracted_text += (p.extract_text() or "") + "\n"

        if len(extracted_text.strip()) > 20:
            return None, f"\n[Extracted Digital PDF Prescription Text]:\n{extracted_text.strip()}"

        for p in reader.pages:
            if hasattr(p, "images") and p.images:
                img_obj = p.images[0]
                mime = "image/png" if img_obj.name.lower().endswith(".png") else "image/jpeg"
                inline_data = {
                    "mimeType": mime,
                    "data": base64.b64encode(img_obj.data).decode("utf-8")
                }
                return inline_data, extracted_text.strip()
    except Exception as e:
        print(f"[pypdf Warning] {e}")

    # Step 3: Raw PDF inline fallback
    inline_data = {
        "mimeType": "application/pdf",
        "data": base64.b64encode(content).decode("utf-8")
    }
    return inline_data, extracted_text.strip()

def prepare_file_for_gemini(filename: str, content: bytes, content_type: str = "") -> Tuple[Optional[Dict[str, str]], str]:
    """
    Universal multi-format dispatcher for PDF, Image, Camera JPEG, CSV, and Word documents.
    Returns (inline_data_dict_or_None, supplementary_text).
    """
    filename_lower = filename.lower()
    inline_data = None
    extra_text = ""

    # 1. PDF Documents (Intelligent text extraction + image rendering)
    if filename_lower.endswith(".pdf") or "pdf" in content_type or b"%PDF" in content[:10]:
        inline_data, extra_text = extract_pdf_content(content)

    # 2. Images & Camera Photos
    elif filename_lower.endswith((".jpg", ".jpeg")) or "jpeg" in content_type:
        inline_data = {
            "mimeType": "image/jpeg",
            "data": base64.b64encode(content).decode("utf-8")
        }
    elif filename_lower.endswith(".png") or "png" in content_type:
        inline_data = {
            "mimeType": "image/png",
            "data": base64.b64encode(content).decode("utf-8")
        }
    elif filename_lower.endswith(".webp") or "webp" in content_type:
        inline_data = {
            "mimeType": "image/webp",
            "data": base64.b64encode(content).decode("utf-8")
        }

    # 3. Word Documents (.docx / .doc)
    elif filename_lower.endswith((".docx", ".doc")):
        text, embedded = extract_docx_content(content)
        extra_text = f"\n[Extracted Word Document Text]:\n{text}" if text else ""
        if embedded:
            mime, b64_img = embedded
            inline_data = {"mimeType": mime, "data": b64_img}

    # 4. CSV & Spreadsheet Files
    elif filename_lower.endswith((".csv", ".tsv", ".txt")) or "csv" in content_type or "text/" in content_type:
        text = decode_text_content(content)
        extra_text = f"\n[Tabular / CSV Document Data]:\n{text}"

    # Default fallback: check magic bytes
    else:
        if b"%PDF" in content[:10]:
            inline_data = {"mimeType": "application/pdf", "data": base64.b64encode(content).decode("utf-8")}
        else:
            inline_data = {"mimeType": "image/jpeg", "data": base64.b64encode(content).decode("utf-8")}

    return inline_data, extra_text

@router.post("/extract")
async def extract_prescription(file: UploadFile = File(...)):
    """
    Universal multi-format prescription extraction endpoint for PDF, Image, Camera photo, CSV, and Word documents.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    inline_data, extra_text = prepare_file_for_gemini(file.filename, content, file.content_type or "")

    prompt = (
        "You are an expert clinical pharmacologist and medical document parser. "
        "Analyze this medical prescription or clinical document (which may be a PDF, handwriting scan, camera photo, Word document, or CSV table). "
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

    if extra_text:
        prompt += f"\n\n{extra_text}"

    try:
        extracted = call_gemini_with_failover(
            prompt=prompt,
            inline_data=inline_data
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
    Universal multi-format clinical rules extraction endpoint for PDF, Image, Camera photo, CSV, and Word documents.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    inline_data, extra_text = prepare_file_for_gemini(file.filename, content, file.content_type or "")

    prompt = (
        "You are an expert clinical pharmacologist. "
        "Analyze this document (which may be a prescription slip, clinical protocol, pharmacology guide, CSV rule matrix, or Word document). "
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

    if extra_text:
        prompt += f"\n\n{extra_text}"

    try:
        extracted = call_gemini_with_failover(
            prompt=prompt,
            inline_data=inline_data
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
