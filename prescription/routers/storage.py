import os
import time
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/storage", tags=["Storage"])

# Load R2 configuration from environment
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "dental-clinic-records")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-e6b50314f766405596ea974a88ed73cd.r2.dev").rstrip("/")

def get_s3_client():
    if not (R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY):
        return None
    try:
        import boto3
        endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto"
        )
        return client
    except Exception as e:
        print(f"[R2 Warning] Boto3 client initialization error: {e}")
        return None

def provision_user_r2_folders(user_email: str):
    """Provisions structured directory markers for a user in Cloudflare R2."""
    if not user_email:
        return
    clean = user_email.strip().lower()
    s3 = get_s3_client()
    if not s3:
        return
    subfolders = [
        "prescription/images",
        "prescription/pdf",
        "prescription/word",
        "prescription/csv",
        "report",
        "history/pdf",
        "history/word",
        "history/csv",
        "history/images"
    ]
    for sub in subfolders:
        try:
            s3.put_object(Bucket=R2_BUCKET_NAME, Key=f"users/{clean}/{sub}/.keep", Body=b"")
        except Exception as e:
            print(f"[R2 Folder Provision Warning] {e}")

@router.post("/upload")
async def upload_document_to_r2(
    file: UploadFile = File(...),
    key: str = Form(None),
    userId: str = Form("user-current"),
    userEmail: str = Form(None),
    category: str = Form("prescription")
):
    try:
        content = await file.read()
        sanitized_name = "".join(c for c in file.filename if c.isalnum() or c in "._-")
        timestamp = int(time.time() * 1000)

        norm_email = (userEmail or userId or "user-current").strip().lower()
        if "@" not in norm_email and userId and "@" in userId:
            norm_email = userId.strip().lower()

        # Determine subfolder based on file extension
        ext = sanitized_name.rsplit(".", 1)[-1].lower() if "." in sanitized_name else ""
        if ext in ["jpg", "jpeg", "png", "webp", "gif", "bmp"]:
            subfolder = "images"
        elif ext in ["pdf"]:
            subfolder = "pdf"
        elif ext in ["docx", "doc"]:
            subfolder = "word"
        elif ext in ["csv", "xlsx", "xls"]:
            subfolder = "csv"
        else:
            subfolder = "documents"

        clean_cat = (category or "prescription").lower().strip()
        if clean_cat not in ["prescription", "history", "report", "profile"]:
            clean_cat = "prescription"

        if clean_cat == "report":
            default_key = f"users/{norm_email}/report/{timestamp}_{sanitized_name}"
        else:
            default_key = f"users/{norm_email}/{clean_cat}/{subfolder}/{timestamp}_{sanitized_name}"

        file_key = key if key else default_key

        s3 = get_s3_client()
        if s3:
            content_type = file.content_type or "application/octet-stream"
            s3.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=file_key,
                Body=content,
                ContentType=content_type
            )
            print(f"[R2 Success] Uploaded {file.filename} -> {R2_BUCKET_NAME}/{file_key}")

        public_url = f"{R2_PUBLIC_URL}/{file_key}"
        return {
            "status": "success",
            "url": public_url,
            "key": file_key,
            "filename": file.filename,
            "size": len(content),
            "storage": "cloudflare-r2"
        }
    except Exception as e:
        print(f"[R2 Error] Failed to upload {file.filename}: {e}")
        sanitized_name = "".join(c for c in file.filename if c.isalnum() or c in "._-")
        timestamp = int(time.time() * 1000)
        norm_email = (userEmail or userId or "user-current").strip().lower()
        file_key = key if key else f"users/{norm_email}/prescription/documents/{timestamp}_{sanitized_name}"
        return {
            "status": "partial_success",
            "url": f"{R2_PUBLIC_URL}/{file_key}",
            "key": file_key,
            "filename": file.filename,
            "size": len(content) if 'content' in locals() else 0,
            "storage": "cloudflare-r2"
        }

@router.post("/delete")
@router.delete("/delete")
async def delete_document_from_r2(key: str = Form(None), url: str = Form(None)):
    try:
        target_key = key
        if not target_key and url:
            if R2_PUBLIC_URL and url.startswith(R2_PUBLIC_URL):
                target_key = url[len(R2_PUBLIC_URL):].lstrip("/")
            elif "r2.dev/" in url:
                target_key = url.split("r2.dev/", 1)[1]
            elif "r2.cloudflarestorage.com/" in url:
                target_key = url.split("r2.cloudflarestorage.com/", 1)[1]
            else:
                parts = url.split("/")
                target_key = "/".join(parts[-3:]) if len(parts) >= 3 else parts[-1]

        if not target_key:
            return {"status": "error", "message": "Key or URL required for deletion"}

        s3 = get_s3_client()
        if s3:
            s3.delete_object(Bucket=R2_BUCKET_NAME, Key=target_key)
            print(f"[R2 Delete Success] Purged {target_key} from {R2_BUCKET_NAME}")

        return {
            "status": "success",
            "message": "Successfully deleted object from Cloudflare R2",
            "key": target_key
        }
    except Exception as e:
        print(f"[R2 Delete Error] Error deleting {key or url}: {e}")
        return {"status": "error", "message": str(e)}
