"""
Smile Clinic Backend Entry Point
Delegates directly to the Prescription Service API.
"""
import os
import uvicorn
from prescription.main import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("prescription.main:app", host=host, port=port, reload=True)
