import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables cleanly from prescription/.env or system env
env_file = Path(__file__).resolve().parent / ".env"
if env_file.exists():
    load_dotenv(env_file, override=False)
else:
    load_dotenv(override=False)

from .database import engine, Base
from .routers import auth, storage, extractor, sync, checks

# Auto-initialize database tables if not existing
try:
    if engine:
        Base.metadata.create_all(bind=engine)
        print("[Prescription DB] Tables initialized successfully.")
except Exception as e:
    print(f"[Prescription DB Warning] Table creation skipped: {e}")

app = FastAPI(
    title="Smile Clinic - Prescription Service API",
    description="Dedicated microservice for Smile Clinic clinician authentication and prescription safety workflows.",
    version="1.0.1"
)

FRONTEND_URL = os.getenv("FRONTEND_URL")
DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://prescription-dentalclinic.pages.dev",
    "https://prescription-dental-clinic.vercel.app"
]
if FRONTEND_URL:
    DEFAULT_ORIGINS.insert(0, FRONTEND_URL.rstrip("/"))

env_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
ALLOWED_ORIGINS = list(dict.fromkeys(DEFAULT_ORIGINS + env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if "*" not in ALLOWED_ORIGINS else ["*"],
    allow_origin_regex=r"https:\/\/.*\.pages\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    origin = request.headers.get("origin", "*") or "*"
    return JSONResponse(
        status_code=500,
        content={"detail": f"Clinical server error: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

app.include_router(auth.router)
app.include_router(storage.router)
app.include_router(extractor.router)
app.include_router(sync.router)
app.include_router(checks.router)

@app.get("/")
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "SmileClinic-PrescriptionBackend",
        "version": "1.0.2",
        "storage": "persistent-sqlite"
    }
