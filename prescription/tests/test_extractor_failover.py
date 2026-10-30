import pytest
from fastapi.testclient import TestClient
from prescription.main import app

client = TestClient(app)

def test_extract_missing_file_422():
    response = client.post("/api/prescriptions/extract")
    assert response.status_code == 422

def test_extract_empty_file_400():
    response = client.post(
        "/api/prescriptions/extract",
        files={"file": ("empty.pdf", b"", "application/pdf")}
    )
    assert response.status_code == 400
    assert "empty" in response.json().get("detail", "").lower()

