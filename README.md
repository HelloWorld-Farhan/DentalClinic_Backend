<h1 align="center">🏥 Smile Clinic Core API — Enterprise Dental Backend Ecosystem</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python_3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/PostgreSQL_15+-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
  <img src="https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase"/>
  <img src="https://img.shields.io/badge/SQLAlchemy_2.0-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy"/>
  <img src="https://img.shields.io/badge/Render-46E3B7?style=for-the-badge&logo=render&logoColor=white" alt="Render"/>
  <img src="https://img.shields.io/badge/License-MIT-brightgreen?style=for-the-badge" alt="MIT License"/>
</p>

<p align="center">
  <strong>Smile Clinic Core API (DentalClinic_Backend)</strong> is the enterprise clinical decision support and centralized backend engine powering the complete Smile Clinic healthcare ecosystem.<br/>
  It provides asynchronous pharmacological interaction screening, multi-tenant role authorization, patient EHR management, immutable audit trails,<br/>
  and permanent cloud data persistence via PostgreSQL on Supabase.
</p>

---

## ⚡ Core API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness & readiness probe for 24/7 keep-alive monitoring (UptimeRobot). |
| `POST` | `/api/v1/auth/register` | Clinician & pharmacist registration with hashed passwords (BCrypt). |
| `POST` | `/api/v1/auth/login` | Secure JWT bearer token issue with 7-day expiration. |
| `POST` | `/api/v1/prescriptions/check` | Real-time drug-drug interaction & allergy cross-sensitivity screening. |
| `GET` | `/api/v1/prescriptions/audit` | Chronological HIPAA compliance audit log of all clinical reviews. |
| `GET` | `/docs` | Interactive Swagger UI API documentation and live test console. |
| `GET` | `/redoc` | OpenAPI specification and production endpoint documentation. |

---

## ✨ Features

| Feature | Description |
|---|---|
| 🛡️ **Prescription CDS Safety Engine** | High-speed automated rule evaluation detecting contraindicated drug pairings (e.g. Amoxicillin + Methotrexate, NSAID + Anticoagulants). |
| 🗄️ **Permanent PostgreSQL on Supabase** | Enterprise relational storage with ACID guarantees, zero data loss, and transaction connection pooling. |
| 🔒 **Enterprise Auth & Zero-Trust Security** | Salted BCrypt password hashing, 256-bit signed JWT session tokens, and strict role segregation (`DOCTOR`, `PHARMACIST`, `ADMIN`). |
| 🚫 **Zero Hardcoding Architecture** | Strict environment separation with zero hardcoded credentials; all secrets dynamically resolved via environment variables. |
| 💓 **Render 24/7 Keep-Alive Watcher** | Dedicated `/health` probe optimized for UptimeRobot 10-minute cron pings, preventing cold starts on cloud containers. |
| 🌐 **CORS Multi-Origin Edge Gateway** | Cross-Origin Resource Sharing pre-configured for Cloudflare Pages, custom subdomains, and local developer workstations. |
| 🧩 **Modular Clean Architecture** | Modular sub-service design enabling isolated expansion for Prescription, Doctor, Patient, and Admin portals. |

---

## 💻 How to Run Locally (For Developers)

### Prerequisites
* **Python 3.11+** installed on your system.
* **Git** installed on your system.

### Step 1 — Clone the Repository

```bash
git clone https://github.com/HelloWorld-Farhan/DentalClinic_Backend.git
cd DentalClinic_Backend
```

### Step 2 — Create and Activate Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Configure Local Environment File

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.xxxx.supabase.co:5432/postgres
JWT_SECRET=your_super_secret_jwt_key_here
PORT=8000
```

> ⚠️ **Note:** `.env` is permanently ignored by `.gitignore` and must **never** be committed to GitHub.

### Step 5 — Start the FastAPI Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> The API will be running live at `http://localhost:8000`.  
> Interactive API Docs (Swagger): `http://localhost:8000/docs`

---

## 📁 Project Structure

```text
DentalClinic_Backend/
├── .gitignore                   # Strictly blocks .env, *.db, and __pycache__
├── SECURITY_RULES.md            # Zero-hardcoding enforcement policy
├── ENV_REFERENCE.md             # Full reference of environment variables
├── README.md                    # Comprehensive architecture documentation
├── requirements.txt             # Root production dependencies
├── main.py                      # Root FastAPI entrypoint (delegates to prescription service)
└── prescription/                # 💊 Modular Prescription Backend Service
    ├── __init__.py              # Package marker
    ├── main.py                  # Standalone FastAPI service with /health & CORS
    ├── database.py              # Supabase PostgreSQL engine + SQLite dev fallback
    ├── models.py                # Clinician User & AuthOtp database models
    ├── schemas.py               # Pydantic request/response schemas with regex validation
    ├── requirements.txt         # Module dependencies
    ├── ENV_REFERENCE.md         # Prescription service environment guide
    ├── google_apps_script.js    # Production Google Apps Script email gateway source
    ├── test_api_endpoints.py    # Automated test suite (Signup -> OTP -> Login)
    └── routers/
        ├── __init__.py
        └── auth.py              # Signup, OTP verification & login endpoints
```

---

## 🚀 Cloud Deployment to Render

1. Log into your **[Render Dashboard](https://dashboard.render.com)**.
2. Click **New +** $\rightarrow$ **Web Service**.
3. Connect your GitHub repository: `HelloWorld-Farhan/DentalClinic_Backend`.
4. Configure the build parameters:
   * **Runtime:** `Python 3`
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Under **Environment Variables**, add:
   * `DATABASE_URL` = *(Your Supabase connection string)*
   * `JWT_SECRET` = *(Your secure secret string)*
6. Click **Deploy Web Service**.
7. *(Optional Keep-Alive)*: Add your Render URL (`https://your-service.onrender.com/health`) as an HTTP monitor in **[UptimeRobot](https://uptimerobot.com)** every 10 minutes to keep it awake 24/7.

---

## 👨‍💻 Author

**Farhan Khalid**

📧 [farhankhalid17968@gmail.com](mailto:farhankhalid17968@gmail.com)  
🔗 [LinkedIn](https://www.linkedin.com/in/farhan-khalid-117514259/)  
🐙 [GitHub](https://github.com/HelloWorld-Farhan)

---

## 📄 License

```text
MIT License

Copyright (c) 2026 Farhan Khalid

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is furnished
to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🌟 Support

If you found this backend architecture helpful, please consider giving it a ⭐ on GitHub!

<p align="center">Made with ❤️ in India</p>
