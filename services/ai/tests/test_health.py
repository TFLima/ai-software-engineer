from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ai"}


def test_analysis_and_docs_are_not_implemented():
    assert client.post("/internal/v1/analyses:run", json={}).status_code == 404
    assert client.get("/docs").status_code == 404
