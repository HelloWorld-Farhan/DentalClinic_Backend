# Backend Environment Variables Reference Guide (Prescription Service)

> **Project:** `DentalClinic_Backend / Prescription` (Python 3.11 + FastAPI)  
> **Location:** Local `.env` & Render Dashboard Environment Secrets

This document details every environment variable used in the Prescription Service backend, what service it connects to, and why it is needed.

---

## Complete Variables Table

| Variable Name | Provider / Target | Purpose & Description | Where it is Used in Code |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | **Supabase PostgreSQL** | The primary database connection string (`postgresql://postgres:...@db.eikncobxyhvpnoondfqk.supabase.co:5432/postgres`). | SQLAlchemy `create_engine()` to store and query permanent tables |
| `DB_PASSWORD` | **Supabase** | The password (`Dental@2026#`) for database admin connections. | Backup credential reference |
| `SUPABASE_URL` | **Supabase** | The root HTTPS project endpoint (`https://eikncobxyhvpnoondfqk.supabase.co`). | Direct API fallback |
| `BACKEND_URL` | **Render Web Service** | The public URL of this live FastAPI server (`https://dentalclinic-backend-eiav.onrender.com`). | Webhook callbacks & keep-alive logging |
| `GOOGLE_APPS_SCRIPT_URL` | **Google Apps Script** | Webhook URL sending clinical OTP & welcome emails directly via `support.smileclinic@gmail.com`. | Email service (`send_template_email`) |
| `FIREBASE_PROJECT_ID` | **Google Firebase (Auth Only)** | The project identifier (`smileclinic-auth`) used by backend to cryptographically verify Google ID tokens. | Google 1-Click Auth verification |
| `FIREBASE_AUTH_DOMAIN` | **Google Firebase (Auth Only)** | The authentication domain (`smileclinic-auth.firebaseapp.com`) for Google OAuth token audience checking. | Google 1-Click Auth verification |
| `FIREBASE_STORAGE_BUCKET`| **Firebase Storage (Later)** | Cloud storage bucket (Unused for now; reserved for future file attachments). | Inactive for now |

| `JWT_SECRET` | **Internal Auth** | A secret 256-bit encryption key used to sign and verify clinician JWT session tokens. | `jose.jwt.encode()` & `decode()` |
| `PORT` | **Render Linux Container**| The network port assigned by Render dynamically (defaults to `8000` locally). | `uvicorn.run()` |

---

## Security Reminders
1. Backend variables are loaded dynamically using `os.getenv("KEY")`.
2. **NEVER** write default passwords into `.py` code. Always raise an error or fall back to local test SQLite if unset.
3. In production, configure these variables in **Render Dashboard $\rightarrow$ Web Service $\rightarrow$ Environment Secrets**.
