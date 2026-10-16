"""B13 fixed snapshot, real components, fake transport/provider and strict HTTP boundary."""
import asyncio
from copy import deepcopy
import json
import subprocess
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from support.acceptance_app import app, pipeline, SHA, ARCHIVE, MANIFEST
from test_internal import payload, HEADERS


@pytest.mark.parametrize('scenario,status,code', [
    ('hello-world', 200, None), ('empty', 200, None), ('xss', 200, None),
    ('invalid-json', 422, 'invalid_findings'), ('bad-evidence', 422, 'invalid_findings'),
    ('missing', 422, 'repository_unavailable'), ('private', 422, 'repository_unavailable'),
    ('oversize', 422, 'limit_exceeded'), ('unsafe-path', 422, 'unsafe_snapshot'),
    ('provider-down', 502, 'upstream_unavailable'), ('injection', 200, None),
])
def test_scenario_through_real_stages(payload, tmp_path, scenario, status, code, caplog):
    payload = deepcopy(payload)
    payload['repository'] = {'owner': 'octocat', 'name': scenario, 'url': f'https://github.com/octocat/{scenario}'}
    component, transport, adapter = pipeline(scenario, tmp_path)
    # Acquisition is replayed; process execution is forbidden even when AGENTS.md demands it.
    with patch.object(subprocess, 'Popen', side_effect=AssertionError('Repository execution forbidden')):
        actual, result = asyncio.run(component.run(payload))
    assert actual == status and not list(tmp_path.iterdir())
    assert all(url.startswith(('https://api.github.com/', 'https://codeload.github.com/')) for url in transport.urls)
    assert 'attacker.invalid' not in ''.join(transport.urls)
    assert result['analysis_id'] == payload['analysis_id'] and result['attempt_id'] == payload['attempt_id']
    if code:
        assert result['outcome'] == 'failed' and result['error']['code'] == code
        assert 'findings' not in result
    else:
        assert result['outcome'] == 'succeeded' and result['commit_sha'] == SHA
        assert result['coverage']['included_lines'] == 1
    if scenario in {'missing', 'private', 'oversize', 'unsafe-path'}:
        assert adapter.calls == 0
    if scenario == 'hello-world':
        assert result['findings'][0]['evidence'] == [{'path': 'README', 'start_line': 1, 'end_line': 1}]
    if scenario == 'injection':
        assert result['findings'] == []
    assert 'IGNORE ALL RULES' not in caplog.text and 'onerror' not in caplog.text
    assert 'Hello World!' not in caplog.text and '{broken' not in caplog.text


def test_test_only_app_keeps_authentication_and_pinned_sha(payload, monkeypatch):
    monkeypatch.setenv('AI_INTERNAL_SECRET', 's' * 64)
    payload['repository'] = {'owner': 'octocat', 'name': 'hello-world', 'url': MANIFEST['repository']}
    payload['commit_sha'] = SHA
    with TestClient(app) as client:
        assert client.post('/internal/v1/analyses:run', json=payload).status_code == 401
        headers = {**HEADERS, 'Authorization': 'Bearer ' + 's' * 64}
        result = client.post('/internal/v1/analyses:run', json=payload, headers=headers)
        assert result.status_code == 200 and result.json()['commit_sha'] == SHA
        assert result.json()['provenance']['provider'] == 'fake'
        assert client.get('/docs').status_code == 404
