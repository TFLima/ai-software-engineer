from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
from fastapi.testclient import TestClient
from app.limits import CEILINGS
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AI_INTERNAL_SECRET", "s" * 64)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def payload():
    return {"schema_version": 1, "finding_schema_version": 1,
            "analysis_id": "11111111-1111-4111-8111-111111111111",
            "attempt_id": "22222222-2222-4222-8222-222222222222", "attempt_number": 1,
            "repository": {"owner": "example", "name": "small-app", "url": "https://github.com/example/small-app"},
            "commit_sha": None, "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=239)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "selection_policy_version": "1", "context_policy_version": "1", "prompt_version": "1", "limits": deepcopy(CEILINGS)}


HEADERS = {"Authorization": "Bearer " + "s" * 64, "Content-Type": "application/json"}


def test_auth_before_body_validation(client):
    for authorization in (None, "Bearer wrong", "Basic " + "s" * 64):
        headers = {} if authorization is None else {"Authorization": authorization}
        response = client.post("/internal/v1/analyses:run", content="bad" * 40000, headers=headers)
        assert response.status_code == 401
        assert response.json() == {"schema_version": 1, "error": {"code": "unauthorized_internal", "stage": "request", "retryable": False}}


def test_valid_request_fails_closed_without_pipeline(client, payload):
    payload["commit_sha"] = "a" * 40
    response = client.post("/internal/v1/analyses:run", json=payload, headers=HEADERS)
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "configuration_error"
    assert body["attempt_id"] == payload["attempt_id"]
    assert body["commit_sha"] == "a" * 40
    assert "findings" not in body and body["coverage"] is None


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(tools=["shell"]),
    lambda p: p.update(attempt_number=True),
    lambda p: p.update(attempt_number=4),
    lambda p: p.update(attempt_id="not-a-uuid"),
    lambda p: p.update(commit_sha="bad"),
    lambda p: p["repository"].update(url="http://localhost/repo"),
    lambda p: p["repository"].update(extra="bad"),
    lambda p: p["limits"].update(file_count=True),
    lambda p: p["limits"].update(file_count=0),
    lambda p: p["limits"].update(file_count=2001),
    lambda p: p["limits"].update(file_count=1),
    lambda p: p["limits"].update(overall_seconds=1),
    lambda p: p["limits"].update(attempt_tokens=1),
    lambda p: p.update(deadline_at="2000-01-01T00:00:00Z"),
    lambda p: p.update(deadline_at="2099-01-01T00:00:00Z"),
])
def test_invalid_contract(client, payload, mutation):
    mutation(payload)
    response = client.post("/internal/v1/analyses:run", json=payload, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("key,value", [("schema_version", 2), ("schema_version", True), ("finding_schema_version", 2), ("prompt_version", "2")])
def test_unsupported_versions(client, payload, key, value):
    payload[key] = value
    response = client.post("/internal/v1/analyses:run", json=payload, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_schema"


@pytest.mark.parametrize("body", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{', '{} trailing', b'\xff', '{"x":{"a":1,"a":2}}'])
def test_strict_json(client, body):
    assert client.post("/internal/v1/analyses:run", content=body, headers=HEADERS).status_code == 400


def test_body_media_type_and_object_root(client):
    assert client.post("/internal/v1/analyses:run", content="x" * 32769, headers=HEADERS).status_code == 413
    assert client.post("/internal/v1/analyses:run", content="[]", headers=HEADERS).status_code == 422
    assert client.post("/internal/v1/analyses:run", content="{}", headers={"Authorization": HEADERS["Authorization"]}).status_code == 415


def test_single_active_slot(client, payload):
    async def lock():
        await app.state.slot.acquire()
    client.portal.call(lock)
    try:
        response = client.post("/internal/v1/analyses:run", json=payload, headers=HEADERS)
        assert response.status_code == 503
        assert response.json()["error"] == {"code": "upstream_unavailable", "stage": "request", "retryable": True}
    finally:
        client.portal.call(app.state.slot.release)


def test_missing_secret_blocks_startup(monkeypatch):
    monkeypatch.delenv("AI_INTERNAL_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="configuration"):
        with TestClient(app):
            pass
