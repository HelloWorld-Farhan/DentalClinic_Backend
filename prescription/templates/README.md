# 📧 Smile Clinic Email Templates Reference & Gallery

All templates in this folder are designed to match the **Smile Clinic RxGuard UI** design system (Inter typography, hospital-grade teal/emerald gradients `#005c65` / `#007782`, subtle CSS keyframe pulse animations, high-contrast dark/light adaptability, and mobile-responsive email table layouts).

All templates prominently feature the official technical & clinical support contact:
**`support.smileclinic@gmail.com`**

---

## 📁 Template Directory Overview

| # | File Name | Purpose & Trigger | Key Dynamic Variables |
|---|---|---|---|
| **1** | [`otp_verification.html`](file:///d:/Dental_Clinic/templates/otp_verification.html) | Account Signup 6-digit verification code with glowing animated border & countdown. | `{{ clinician_name }}`, `{{ otp_code }}`, `{{ expires_in_minutes }}` |
| **2** | [`welcome_clinician.html`](file:///d:/Dental_Clinic/templates/welcome_clinician.html) | Welcome email upon successful registration/activation showing registered email. | `{{ clinician_name }}`, `{{ clinician_email }}`, `{{ portal_login_url }}` |
| **3** | [`password_reset_otp.html`](file:///d:/Dental_Clinic/templates/password_reset_otp.html) | Password reset authorization OTP with security alert badge and incident link. | `{{ clinician_name }}`, `{{ clinician_email }}`, `{{ reset_code }}`, `{{ expires_in_minutes }}` |
| **4** | [`prescription_safety_alert.html`](file:///d:/Dental_Clinic/templates/prescription_safety_alert.html) | High-severity interaction alert (Contraindicated / Major drug pairings flagged). | `{{ prescriber_name }}`, `{{ patient_name }}`, `{{ patient_mrn }}`, `{{ severity_level }}`, `{{ proposed_drug }}`, `{{ conflict_agent }}`, `{{ interaction_mechanism }}`, `{{ review_url }}` |
| **5** | [`prescription_dispense_copy.html`](file:///d:/Dental_Clinic/templates/prescription_dispense_copy.html) | Clinical review & dispense copy cleared for pharmacy dispensing with QR/Hash. | `{{ recipient_name }}`, `{{ rx_number }}`, `{{ patient_name }}`, `{{ patient_mrn }}`, `{{ doctor_name }}`, `{{ doctor_npi }}`, `{{ medication_details }}`, `{{ directions_sig }}`, `{{ verification_hash }}` |

---

## ⚡ How to Send with Google Apps Script in Python (FastAPI Backend)

```python
import os
import requests

GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL")

def send_template_email(to_email: str, subject: str, template_name: str, context: dict):
    template_path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", template_name)
    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Replace placeholders
    for key, value in context.items():
        html_content = html_content.replace(f"{{{{ {key} }}}}", str(value))

    return requests.post(
        GOOGLE_APPS_SCRIPT_URL,
        json={
            "to": to_email,
            "subject": subject,
            "html": html_content
        },
        timeout=10
    )
```
