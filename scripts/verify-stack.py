#!/usr/bin/env python3
"""Verify B02 health, routing, private services and loopback exposure."""
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {"nginx", "frontend", "api", "worker", "ai", "postgres", "redis"}


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def compose(*args):
    return run("docker", "compose", *args)


def request(path, *, headers=None, expected=200, method="GET"):
    req = urllib.request.Request("http://127.0.0.1:8080" + path, headers=headers or {}, method=method)
    # Local verification never uses an inherited HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.status == expected, (path, response.status, expected)
        return response.read().decode()


def main():
    config = json.loads(compose("config", "--format", "json"))
    assert set(config["services"]) == EXPECTED
    assert [name for name, service in config["services"].items() if service.get("ports")] == ["nginx"]
    assert not any(key.startswith("DB_") for key in config["services"]["ai"].get("environment", {}))
    for name in sorted(EXPECTED):
        container = json.loads(run("docker", "inspect", compose("ps", "-q", name)))[0]
        assert container["State"]["Running"], name
        assert container["State"]["Health"]["Status"] == "healthy", name
        assert container["HostConfig"]["Memory"] > 0, name
        assert container["HostConfig"]["NanoCpus"] > 0, name
        if name in {"api", "worker", "ai"}:
            assert container["Config"]["User"] not in {"", "root", "0"}, name
        environment_keys = {entry.split("=", 1)[0] for entry in container["Config"].get("Env", [])}
        if name == "ai":
            assert not any(key.startswith("DB_") for key in environment_keys), name
        if name in {"nginx", "frontend", "ai"}:
            assert not {"APP_KEY", "DB_PASSWORD"} & environment_keys, name
        bindings = container["HostConfig"].get("PortBindings") or {}
        if name == "nginx":
            assert bindings == {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8080"}]}, bindings
        else:
            assert not bindings, (name, bindings)
        print(f"PASS {name}: healthy, expected port bindings")

    assert json.loads(request("/healthz")) == {"status": "ok", "service": "nginx"}
    assert json.loads(request("/api/health")) == {"status": "ok", "service": "application"}
    html = request("/")
    assert "<app-root>" in html
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
    assert scripts
    for script in scripts:
        assert request("/" + script.lstrip("/"))
    for headers in ({"Host": "attacker.example:8080"}, {"Origin": "https://attacker.example"}, {"Origin": "null"}):
        assert json.loads(request("/api/health", headers=headers, expected=403))["error"]["code"] == "access_denied"
    request("/api/health", headers={"Origin": "http://localhost:8080"})
    request("/internal/v1/analyses:run", expected=404, method="POST")
    request("/api/analyses", expected=404, method="POST")
    print("PASS edge: Angular assets, Laravel readiness, Host/Origin policy, absent analysis/internal routes")

    assert json.loads(compose("exec", "-T", "frontend", "wget", "-Y", "off", "-qO-", "http://127.0.0.1:8080/healthz"))["service"] == "frontend"
    ai = compose("exec", "-T", "worker", "php", "-r", "echo file_get_contents('http://ai:8000/health');")
    assert json.loads(ai) == {"status": "ok", "service": "ai"}
    assert compose("exec", "-T", "redis", "redis-cli", "ping") == "PONG"
    sql = "SELECT 1; SELECT name FROM pg_available_extensions WHERE name = 'vector'; SELECT count(*) FROM pg_extension WHERE extname = 'vector';"
    assert compose("exec", "-T", "postgres", "psql", "-U", "ai_software_engineer", "-d", "ai_software_engineer", "-Atc", sql).splitlines() == ["1", "vector", "0"]
    compose("exec", "-T", "worker", "php", "worker-health.php")
    print("PASS internal: FastAPI reachable from worker, Redis PONG, PostgreSQL SQL, pgvector available and unused, worker alive")


if __name__ == "__main__":
    main()
