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

### Python Backend Standard:
```python
import os

# ALWAYS read from environment; NEVER hardcode credentials
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is missing. Set it in .env or Render Dashboard.")

JWT_SECRET = os.getenv("JWT_SECRET")
```

---

## 3. Production Environment Secrets
* For **Render** deployment: Enter `DATABASE_URL`, `JWT_SECRET`, and other secrets directly inside:
  **Render Dashboard $\rightarrow$ Web Service $\rightarrow$ Environment $\rightarrow$ Add Environment Variable**.
* Local development: Use `.env` file on your local machine only.
