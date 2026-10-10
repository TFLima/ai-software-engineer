import asyncio
import json
import tarfile

import pytest
from app.main import app
from app.orchestrator import AnalysisOrchestrator
from app.llm_client import BoundedLLMClient, ModelReply, Usage, LLMError
from app.fake_llm import FakeLLMAdapter
from test_repository_reader import reader, archive, SHA, META, deadline
from test_internal import payload, client, HEADERS


def pipeline(tmp_path, replies=None, data=None):
    component, transport = reader(tmp_path, data=data)
    adapter = FakeLLMAdapter(replies)
    return AnalysisOrchestrator(component, lambda: BoundedLLMClient(adapter)), transport, adapter


def test_authenticated_endpoint_runs_real_components(client, payload, tmp_path):
    orchestrator, transport, adapter = pipeline(tmp_path)
    app.state.orchestrator = orchestrator
    response = client.post('/internal/v1/analyses:run', json=payload, headers=HEADERS)
    assert response.status_code == 200
    result = response.json()
    assert result['outcome'] == 'succeeded' and result['findings'] == []
    assert result['commit_sha'] == SHA and result['attempt_id'] == payload['attempt_id']
    assert result['coverage']['included_spans'] == [{'path': 'README.md', 'start_line': 1, 'end_line': 1}]
    assert all(type(v) is int for v in result['stage_durations_ms'].values())
    assert result['provenance']['provider'] == 'fake'
    assert len(transport.urls) == 3 and adapter.calls == 1
    assert list(tmp_path.iterdir()) == []


def test_findings_are_validated_and_trimmed(payload, tmp_path):
    candidate = {'schema_version': 1, 'findings': [{
        'category': 'testing', 'severity': 'low', 'title': ' Advisory ',
        'explanation': 'Consider reviewing this documentation.', 'recommendation': 'Consider adding examples.',
        'evidence': [{'path': 'README.md', 'start_line': 1, 'end_line': 1}]}]}
    orchestrator, _, _ = pipeline(tmp_path, [ModelReply(json.dumps(candidate), Usage(100, 20))])
    status, result = asyncio.run(orchestrator.run(payload))
    assert status == 200 and result['findings'][0]['title'] == 'Advisory'
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('reply,code,status', [
    (ModelReply('{broken', Usage(100, 20)), 'invalid_findings', 422),
    (LLMError('configuration_error'), 'configuration_error', 500),
    (LLMError('upstream_unavailable'), 'upstream_unavailable', 502),
])
def test_failure_preserves_provenance_without_candidate(payload, tmp_path, reply, code, status):
    orchestrator, _, _ = pipeline(tmp_path, [reply, reply])
    actual, result = asyncio.run(orchestrator.run(payload))
    assert actual == status and result['error']['code'] == code
    assert result['commit_sha'] == SHA and result['coverage']['included_lines'] == 1
    assert result['provenance']['provider'] == 'fake' and 'findings' not in result
    assert not list(tmp_path.iterdir())


def test_selection_failure_never_calls_provider(payload, tmp_path):
    data = archive([('root/.env', b'SECRET=value\n', tarfile.REGTYPE)])
    orchestrator, _, adapter = pipeline(tmp_path, data=data)
    status, result = asyncio.run(orchestrator.run(payload))
    assert status == 422 and result['error']['code'] == 'no_eligible_context'
    assert result['commit_sha'] == SHA and result['coverage'] is None
    assert adapter.calls == 0 and not list(tmp_path.iterdir())


def test_crash_and_cancellation_cleanup(payload, tmp_path):
    orchestrator, _, adapter = pipeline(tmp_path)
    class Crash:
        def select(self, *args):
            raise RuntimeError('private source text')
    orchestrator.selector = Crash()
    status, result = asyncio.run(orchestrator.run(payload))
    assert status == 500 and result['error']['code'] == 'invalid_result'
    assert 'private source' not in json.dumps(result) and adapter.calls == 0
    assert not list(tmp_path.iterdir())

    orchestrator, _, _ = pipeline(tmp_path)
    async def cancel(request):
        raise asyncio.CancelledError
    client = BoundedLLMClient(FakeLLMAdapter())
    client.generate = cancel
    orchestrator.client_factory = lambda: client
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(orchestrator.run(payload))
    assert not list(tmp_path.iterdir())


def test_pinned_sha_and_download_failure(payload, tmp_path):
    from test_repository_reader import FakeTransport
    from app.repository_reader import RepositoryReader
    payload['commit_sha'] = SHA
    transport = FakeTransport([(200, {}, META), (404, {}, b'')])
    orchestrator = AnalysisOrchestrator(RepositoryReader(transport, tmp_path),
                                       lambda: BoundedLLMClient(FakeLLMAdapter()))
    status, result = asyncio.run(orchestrator.run(payload))
    assert status == 422 and result['commit_sha'] == SHA
    assert len(transport.urls) == 2 and transport.urls[-1].endswith(SHA)
    assert not list(tmp_path.iterdir())


def test_stage_timeout_preserves_context_and_cleans(payload, tmp_path):
    orchestrator, _, _ = pipeline(tmp_path)
    client = BoundedLLMClient(FakeLLMAdapter())
    async def stall(request):
        await asyncio.sleep(5)
    client.generate = stall
    orchestrator.client_factory = lambda: client
    payload['limits']['generate_seconds'] = 1
    status, result = asyncio.run(orchestrator.run(payload))
    assert status == 504 and result['error']['stage'] == 'generate'
    assert result['commit_sha'] == SHA and result['coverage']['included_lines'] == 1
    assert result['stage_durations_ms']['generate'] == 1000
    assert not list(tmp_path.iterdir())


def test_expired_deadline_performs_no_work(payload, tmp_path):
    orchestrator, transport, adapter = pipeline(tmp_path)
    payload['deadline_at'] = '2000-01-01T00:00:00Z'
    status, result = asyncio.run(orchestrator.run(payload))
    assert status == 504 and result['error']['stage'] == 'request'
    assert not transport.urls and adapter.calls == 0 and not list(tmp_path.iterdir())
