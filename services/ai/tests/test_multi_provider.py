"""Provider selection and official Messages translation with no paid/network calls."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from app.anthropic_llm import (AnthropicAdapter, AnthropicConfig, DATA_POLICY, ENDPOINT,
                               MODEL, wire_schema)
from app.finding_validator import FindingValidator, FindingError
from app.llm_client import BoundedLLMClient, CostPolicy, LLMError, Prompt, SYSTEM_V1, Usage
from app.llm_factory import llm_client_from_env
from app.llm_schema import finding_schema
from test_llm_client import request, EMPTY, SOURCE, SECRET


def env():
    return {'LLM_PROVIDER': 'anthropic', 'LLM_REAL_ENABLED': 'true',
            'ANTHROPIC_API_KEY': SECRET, 'ANTHROPIC_DATA_POLICY': DATA_POLICY,
            'ANTHROPIC_SOURCE_DISCLOSURE_ACKNOWLEDGED': 'true',
            'ANTHROPIC_CALL_MICROUSD': '50000', 'ANTHROPIC_ATTEMPT_MICROUSD': '100000',
            'LLM_CALL_CEILING_MICROUSD': '50000', 'LLM_ATTEMPT_CEILING_MICROUSD': '100000'}


def body(candidate=EMPTY, **changes):
    return {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant', 'model': MODEL,
            'content': [{'type': 'text', 'text': candidate}], 'stop_reason': 'end_turn',
            'stop_sequence': None, 'usage': {'input_tokens': 100, 'output_tokens': 20}, **changes}


def client(handler, settings=None):
    return llm_client_from_env(settings or env(), httpx.MockTransport(handler))


def run(value):
    return asyncio.run(value)


def test_anthropic_auth_schema_injection_provenance_and_no_tools(caplog):
    def handler(req):
        assert str(req.url) == ENDPOINT and req.headers['x-api-key'] == SECRET
        assert req.headers['anthropic-version'] == '2023-06-01'
        payload = json.loads(req.content)
        assert payload['system'] == SYSTEM_V1
        assert SOURCE in json.loads(payload['messages'][0]['content'])['source']
        assert not {'tools', 'tool_choice', 'thinking', 'cache_control'} & payload.keys()
        assert payload['output_config']['format']['schema'] == wire_schema(finding_schema(20, 5))
        return httpx.Response(200, json=body())
    result = run(client(handler).generate(request(SOURCE)))
    assert result.usage == Usage(100, 20)
    assert result.provider == 'anthropic' and result.model == MODEL
    assert result.commit_sha == 'a' * 40 and result.reservations.tries == 1
    assert SECRET not in caplog.text and SOURCE not in caplog.text
    FindingValidator().validate(result.candidate_json, result.context, request().limits,
                                datetime.now(timezone.utc) + timedelta(seconds=30))


def test_legacy_openai_default_and_specific_aliases():
    settings = {'LLM_REAL_ENABLED': 'true', 'OPENAI_API_KEY': SECRET,
                'LLM_MODEL': 'gpt-4.1-mini-2025-04-14', 'LLM_CONTEXT_WINDOW': '1047576',
                'LLM_DATA_POLICY': 'standard-abuse-monitoring-30d',
                'LLM_SOURCE_DISCLOSURE_ACKNOWLEDGED': 'true',
                'LLM_INPUT_MICROUSD_PER_MILLION': '400000',
                'LLM_OUTPUT_MICROUSD_PER_MILLION': '1600000',
                'LLM_CALL_MICROUSD': '20000', 'LLM_ATTEMPT_MICROUSD': '40000'}
    assert llm_client_from_env(settings).adapter.provider == 'openai'
    settings['LLM_PROVIDER'] = 'openai'
    settings['OPENAI_MODEL'] = settings.pop('LLM_MODEL')
    settings['OPENAI_MAX_OUTPUT_TOKENS'] = '10000'
    assert llm_client_from_env(settings).adapter.max_output_tokens == 10000


@pytest.mark.parametrize('provider', ['', 'invalid', 'OpenAI', 'anthropic '])
def test_invalid_provider_no_fallback(provider):
    with pytest.raises(LLMError, match='configuration_error'):
        llm_client_from_env({**env(), 'LLM_PROVIDER': provider})


@pytest.mark.parametrize('environment', ['test', 'development'])
def test_fake_explicitly_authorized(environment):
    result = llm_client_from_env({'LLM_PROVIDER': 'fake', 'LLM_ENVIRONMENT': environment,
                                 'LLM_FAKE_ENABLED': 'true'})
    assert result.adapter.provider == 'fake'
    assert run(result.generate(request())).provider == 'fake'


@pytest.mark.parametrize('changes', [{}, {'LLM_FAKE_ENABLED': 'true'},
    {'LLM_FAKE_ENABLED': 'true', 'LLM_ENVIRONMENT': 'production'},
    {'LLM_FAKE_ENABLED': 'true', 'LLM_ENVIRONMENT': 'test', 'LLM_REAL_ENABLED': 'true'}])
def test_fake_requires_all_gates(changes):
    with pytest.raises(LLMError, match='configuration_error'):
        llm_client_from_env({'LLM_PROVIDER': 'fake', **changes})


@pytest.mark.parametrize('key,value', [('ANTHROPIC_API_KEY', ''), ('LLM_REAL_ENABLED', 'false'),
    ('ANTHROPIC_MODEL', 'unreviewed-model'), ('ANTHROPIC_MODEL', ''),
    ('ANTHROPIC_DATA_POLICY', 'standard-abuse-monitoring-30d'),
    ('ANTHROPIC_SOURCE_DISCLOSURE_ACKNOWLEDGED', 'false'),
    ('ANTHROPIC_CONTEXT_WINDOW', '200001'), ('ANTHROPIC_MAX_OUTPUT_TOKENS', '64001'),
    ('ANTHROPIC_INPUT_MICROUSD_PER_MILLION', '999999'),
    ('ANTHROPIC_OUTPUT_MICROUSD_PER_MILLION', '4999999'),
    ('ANTHROPIC_CALL_MICROUSD', '50001'), ('ANTHROPIC_ATTEMPT_MICROUSD', '100001'),
    ('ANTHROPIC_CALL_MICROUSD', '1.1')])
def test_configuration_fails_closed(key, value):
    with pytest.raises(LLMError, match='configuration_error'):
        llm_client_from_env({**env(), key: value})


@pytest.mark.parametrize('key', ['ANTHROPIC_API_KEY', 'ANTHROPIC_DATA_POLICY',
                                  'ANTHROPIC_SOURCE_DISCLOSURE_ACKNOWLEDGED'])
def test_missing_required_setting(key):
    settings = env(); settings.pop(key)
    with pytest.raises(LLMError, match='configuration_error'):
        llm_client_from_env(settings)


@pytest.mark.parametrize('status,code', [(401, 'configuration_error'), (403, 'configuration_error'),
    (400, 'configuration_error'), (429, 'upstream_rate_limited'), (500, 'upstream_unavailable'),
    (529, 'upstream_unavailable'), (504, 'upstream_timeout'), (302, 'invalid_result')])
def test_http_errors_and_no_fake_fallback(status, code):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={'error': {'message': SECRET}}, headers={'Retry-After': '0'})
    with pytest.raises(LLMError, match=code) as caught:
        run(client(handler).generate(request(operation_tries=1)))
    assert len(calls) == 1 and SECRET not in str(caught.value)
    assert caught.value.reservations.tries == 1


@pytest.mark.parametrize('failure,code', [(httpx.ReadTimeout('private'), 'upstream_timeout'),
                                         (httpx.ConnectError('private'), 'network_unavailable')])
def test_transport_errors(failure, code):
    def handler(_):
        raise failure
    with pytest.raises(LLMError, match=code):
        run(client(handler).generate(request(operation_tries=1)))


def test_retry_reserves_again_and_unknown_usage_stays_unknown():
    calls = []
    def handler(_):
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=body())
    result = run(client(handler).generate(request()))
    assert len(calls) == 2 and result.reservations.tries == 2
    assert result.usage == Usage()


@pytest.mark.parametrize('candidate', ['{', '{}', '{"schema_version":1,"findings":[{}]}',
    '{"schema_version":1,"findings":[],"unknown":1}',
    '{"schema_version":1,"schema_version":1,"findings":[]}'])
def test_invalid_candidate_unchanged_then_rejected_locally(candidate):
    result = run(client(lambda _: httpx.Response(200, json=body(candidate))).generate(request()))
    assert result.candidate_json == candidate
    with pytest.raises(FindingError):
        FindingValidator().validate(candidate, result.context, request().limits,
                                    datetime.now(timezone.utc) + timedelta(seconds=30))


@pytest.mark.parametrize('changes,code', [({'model': 'other'}, 'invalid_result'),
    ({'stop_reason': 'max_tokens'}, 'invalid_findings'), ({'stop_reason': 'refusal'}, 'invalid_findings'),
    ({'content': [{'type': 'tool_use', 'name': 'shell'}]}, 'invalid_result'),
    ({'content': []}, 'invalid_result'), ({'unknown': True}, 'invalid_result'),
    ({'usage': {'input_tokens': True, 'output_tokens': 20}}, 'invalid_result'),
    ({'content': [{'type': 'text', 'text': ''}]}, 'invalid_findings')])
def test_invalid_envelope(changes, code):
    with pytest.raises(LLMError, match=code):
        run(client(lambda _: httpx.Response(200, json=body(**changes))).generate(request()))


@pytest.mark.parametrize('data', [b'{', b'{"model":1,"model":2}', b'\xff', b'{"x":NaN}'])
def test_invalid_wire_json(data):
    with pytest.raises(LLMError, match='invalid_result'):
        run(client(lambda _: httpx.Response(200, content=data,
            headers={'content-type': 'application/json'})).generate(request()))


def test_byte_token_and_financial_limits_before_transport():
    def forbidden(_):
        pytest.fail('must reject before transport')
    for req in [request(SOURCE * 1000), request(input_tokens=100, context_tokens=100)]:
        with pytest.raises(LLMError, match='limit_exceeded'):
            run(client(forbidden).generate(req))
    settings = env()
    settings['ANTHROPIC_CALL_MICROUSD'] = '20000'
    settings['ANTHROPIC_ATTEMPT_MICROUSD'] = '40000'
    with pytest.raises(LLMError, match='limit_exceeded'):
        run(client(forbidden, settings).generate(request()))


def test_attempt_budget_prevents_second_transport():
    settings = env(); settings['ANTHROPIC_ATTEMPT_MICROUSD'] = '50000'
    calls = []
    def handler(_):
        calls.append(1); return httpx.Response(503)
    with pytest.raises(LLMError, match='limit_exceeded'):
        run(client(handler, settings).generate(request()))
    assert len(calls) == 1


def test_response_size_and_usage_above_reservation():
    with pytest.raises(LLMError, match='limit_exceeded'):
        run(client(lambda _: httpx.Response(200, json=body())).generate(request(internal_response_bytes=100)))
    with pytest.raises(LLMError, match='limit_exceeded') as caught:
        run(client(lambda _: httpx.Response(200, json=body(usage={
            'input_tokens': 100, 'output_tokens': 6001}))).generate(request()))
    assert caught.value.usage.output_tokens == 6001


def test_cache_read_usage_counted_without_discount():
    result = run(client(lambda _: httpx.Response(200, json=body(usage={
        'input_tokens': 100, 'output_tokens': 20, 'cache_read_input_tokens': 50}))).generate(request()))
    assert result.usage == Usage(150, 20)


def test_schema_transformation_does_not_mutate_original():
    original = finding_schema(20, 5); copy = json.loads(json.dumps(original))
    converted = wire_schema(original)
    assert original == copy
    assert 'maxItems' not in converted['properties']['findings']
    assert '20' in converted['properties']['findings']['description']


def test_documented_zero_usage_metadata_and_standard_service():
    def handler(req):
        assert json.loads(req.content)['service_tier'] == 'standard_only'
        return httpx.Response(200, json=body(usage={
            'input_tokens': 100, 'output_tokens': 20,
            'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0,
            'cache_creation': {'ephemeral_1h_input_tokens': 0, 'ephemeral_5m_input_tokens': 0},
            'output_tokens_details': {'thinking_tokens': 0},
            'server_tool_use': {'web_fetch_requests': 0, 'web_search_requests': 0},
            'service_tier': 'standard', 'speed': 'standard', 'inference_geo': 'global'}))
    assert run(client(handler).generate(request())).usage == Usage(100, 20)


@pytest.mark.parametrize('metadata', [
    {'server_tool_use': {'web_search_requests': 1}},
    {'cache_creation': {'ephemeral_1h_input_tokens': 1}},
    {'output_tokens_details': {'thinking_tokens': True}},
    {'speed': 'fast'}, {'service_tier': 'priority'}])
def test_unrequested_billable_features_rejected_with_usage(metadata):
    with pytest.raises(LLMError, match='invalid_result') as caught:
        run(client(lambda _: httpx.Response(200, json=body(usage={
            'input_tokens': 100, 'output_tokens': 20, **metadata}))).generate(request()))
    assert caught.value.usage == Usage(100, 20)
