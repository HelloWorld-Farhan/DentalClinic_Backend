# CRITICAL SECURITY RULE: ZERO HARDCODED CREDENTIALS

> **MANDATORY POLICY FOR ALL DEVELOPERS AND AGENTS**  
> **Repository:** `Dental_Backend` (Public GitHub)

---

## 1. Absolute Prohibition on Hardcoded Secrets
* **NEVER** write raw database URLs, database passwords, JWT secrets, API keys, or cloud endpoints directly into any code file (`.py`, `.json`, `.yaml`, `.sql`, etc.).
* **NEVER** commit `.env` or `.env.*` files to Git. Both `.env` and `**/.env` are permanently blocked in `.gitignore`.

---

## 2. Dynamic Environment Variable Extraction
All configurations must be read dynamically from environment variables at runtime:

```python
import os

DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL")
JWT_SECRET = os.getenv("JWT_SECRET")
```

---

## 3. Production Environment Secrets
* For **Render** deployment: Configure `DATABASE_URL`, `GOOGLE_APPS_SCRIPT_URL`, `JWT_SECRET`, etc. inside **Render Dashboard -> Web Service -> Environment**.
* Local development: Maintain `.env` on your local workstation only.