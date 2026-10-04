"""Authenticated B04 boundary; the executable analysis pipeline arrives in B05–B10."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hmac
import json
import os
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.limits import CEILINGS

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


@asynccontextmanager
async def lifespan(app: FastAPI):
    secret = os.environ.get("AI_INTERNAL_SECRET", "")
    if len(secret.encode()) < 32:
        raise RuntimeError("Internal authentication configuration is missing")
    app.state.secret = secret
    app.state.slot = asyncio.Lock()
    yield


app = FastAPI(title="Internal AI service", docs_url=None, redoc_url=None,
              openapi_url=None, lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai"}


def early(status: int, code: str = "invalid_request") -> JSONResponse:
    return JSONResponse(status_code=status, content={"schema_version": 1,
                        "error": {"code": code, "stage": "request", "retryable": False}})


def closed(value, keys):
    if type(value) is not dict or value.keys() != set(keys):
        raise ValueError


def pairs(entries):
    result = {}
    for key, value in entries:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def bad_constant(_):
    raise ValueError


def validate(payload):
    closed(payload, ["schema_version", "finding_schema_version", "analysis_id", "attempt_id",
                     "attempt_number", "repository", "commit_sha", "deadline_at",
                     "selection_policy_version", "context_policy_version", "prompt_version", "limits"])
    if any(type(payload[key]) is not int or payload[key] != 1
           for key in ["schema_version", "finding_schema_version"]):
        raise LookupError
    if any(payload[key] != "1" for key in ["selection_policy_version", "context_policy_version", "prompt_version"]):
        raise LookupError
    if any(type(payload[key]) is not str or not UUID.fullmatch(payload[key])
           for key in ["analysis_id", "attempt_id"]):
        raise ValueError
    if type(payload["attempt_number"]) is not int or not 1 <= payload["attempt_number"] <= 3:
        raise ValueError
    sha = payload["commit_sha"]
    if sha is not None and (type(sha) is not str or not SHA.fullmatch(sha)):
        raise ValueError
    repository = payload["repository"]
    closed(repository, ["owner", "name", "url"])
    owner, name = repository["owner"], repository["name"]
    if type(owner) is not str or type(name) is not str or type(repository["url"]) is not str:
        raise ValueError
    if (not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?", owner) or "--" in owner
            or not re.fullmatch(r"[a-z0-9._-]{1,100}", name) or name in (".", "..")
            or repository["url"] != f"https://github.com/{owner}/{name}"):
        raise ValueError
    limits = payload["limits"]
    closed(limits, CEILINGS)
    for key, ceiling in CEILINGS.items():
        if type(limits[key]) is not int or not 0 < limits[key] <= ceiling:
            raise ValueError
    if (limits["context_files"] > limits["file_count"] or limits["archive_bytes"] > limits["download_bytes"]
            or limits["file_bytes"] > limits["extracted_bytes"] or limits["context_tokens"] > limits["input_tokens"]
            or limits["attempt_tokens"] < limits["operation_tries"] * (limits["input_tokens"] + limits["output_tokens"])
            or sum(limits[f"{stage}_seconds"] for stage in ("acquire", "select", "context", "generate", "validate", "cleanup")) > limits["overall_seconds"]):
        raise ValueError
    deadline = payload["deadline_at"]
    if type(deadline) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", deadline):
        raise ValueError
    remaining = (datetime.fromisoformat(deadline.replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()
    if not 0 < remaining <= limits["overall_seconds"]:
        raise ValueError
    return payload


def failure(payload, code, stage="request", retryable=False):
    return {"schema_version": 1, "finding_schema_version": 1,
            "analysis_id": payload["analysis_id"], "attempt_id": payload["attempt_id"],
            "outcome": "failed", "repository": payload["repository"], "commit_sha": payload["commit_sha"],
            "coverage": None, "provenance": None,
            "stage_durations_ms": dict.fromkeys(["acquire", "select", "context", "generate", "validate", "cleanup"]),
            "error": {"code": code, "stage": stage, "retryable": retryable}}


@app.post("/internal/v1/analyses:run")
async def run(request: Request):
    authorization = request.headers.get("authorization", "")
    if not hmac.compare_digest(authorization.encode(), ("Bearer " + request.app.state.secret).encode()):
        return early(401, "unauthorized_internal")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        return early(415)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 32768:
            return early(413)
        body.extend(chunk)
    try:
        payload = json.loads(bytes(body).decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad_constant)
    except (ValueError, UnicodeError, RecursionError):
        return early(400)
    try:
        payload = validate(payload)
    except LookupError:
        return early(422, "unsupported_schema")
    except (ValueError, TypeError, KeyError, OverflowError):
        return early(422)
    if request.app.state.slot.locked():
        return JSONResponse(status_code=503, content=failure(payload, "upstream_unavailable", retryable=True))
    async with request.app.state.slot:
        # Fail closed until RepositoryReader and the B10 pipeline are implemented.
        # This endpoint performs no source/provider calls and never fabricates findings.
        return JSONResponse(status_code=500, content=failure(payload, "configuration_error"))
