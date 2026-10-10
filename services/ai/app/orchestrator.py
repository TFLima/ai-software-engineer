"""Fixed B10 pipeline. All durable writes remain in Laravel."""
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import time

from app.acquisition import AcquisitionError
from app.context_builder import ContextBuilder, ContextError
from app.file_selector import FileSelector, SelectionError
from app.finding_validator import FindingValidator, FindingError
from app.llm_client import GenerationRequest, LLMError, TRANSIENT
from app.openai_llm import openai_client_from_env
from app.repository_reader import RepositoryReader

STAGES = ('acquire', 'select', 'context', 'generate', 'validate', 'cleanup')


def status_for(code):
    return {'network_unavailable': 502, 'upstream_unavailable': 502,
            'upstream_timeout': 504, 'upstream_rate_limited': 429,
            'invalid_result': 500, 'configuration_error': 500}.get(code, 422)


class AnalysisOrchestrator:
    def __init__(self, reader=None, client_factory=openai_client_from_env,
                 selector=None, builder=None, validator=None):
        self.reader = reader or RepositoryReader()
        self.client_factory = client_factory
        self.selector = selector or FileSelector()
        self.builder = builder or ContextBuilder()
        self.validator = validator or FindingValidator()

    async def run(self, payload):
        limits = payload['limits']
        deadline = datetime.fromisoformat(payload['deadline_at'].replace('Z', '+00:00'))
        expires = time.monotonic() + max(0, (deadline - datetime.now(timezone.utc)).total_seconds())
        result = {key: payload[key] for key in
                  ('schema_version', 'finding_schema_version', 'analysis_id', 'attempt_id', 'repository', 'commit_sha')}
        result.update(outcome='failed', coverage=None, provenance=None,
                      stage_durations_ms=dict.fromkeys(STAGES))
        stage = 'request'
        manager = None
        entered = False

        def remaining():
            value = min(expires - time.monotonic(),
                        (deadline - datetime.now(timezone.utc)).total_seconds()) - limits['cleanup_seconds']
            if value <= 0:
                raise LLMError('upstream_timeout')
            return value

        async def execute(name, operation):
            nonlocal stage
            stage = name
            started = time.monotonic()
            try:
                seconds = min(limits[name + '_seconds'], remaining())
                async with asyncio.timeout(seconds):
                    value = operation()
                    if hasattr(value, '__await__'):
                        value = await value
                remaining()
                if time.monotonic() - started > seconds:
                    raise LLMError('upstream_timeout')
                return value
            finally:
                # A timeout is recorded at its configured ceiling; scheduler latency
                # does not make an otherwise valid failure envelope unparseable.
                result['stage_durations_ms'][name] = min(limits[name + '_seconds'] * 1000,
                                                         int((time.monotonic() - started) * 1000))

        try:
            remaining()
            # Validate paid-call policy before acquisition; no fake runtime fallback.
            client = self.client_factory()
            result['provenance'] = {key: payload[key] for key in
                                    ('finding_schema_version', 'selection_policy_version', 'context_policy_version', 'prompt_version')}
            result['provenance'].update(provider=client.adapter.provider, model=client.adapter.model,
                                        usage={'input_tokens': None, 'output_tokens': None})
            manager = self.reader.snapshot(payload['repository'], payload['commit_sha'], limits, deadline,
                                           on_sha=lambda sha: result.update(commit_sha=sha))
            async def acquire():
                nonlocal entered
                snapshot = await manager.__aenter__()
                entered = True
                return snapshot
            snapshot = await execute('acquire', acquire)
            result['commit_sha'] = snapshot.commit_sha
            if payload['commit_sha'] is not None and snapshot.commit_sha != payload['commit_sha']:
                raise LLMError('invalid_result')
            selection = await execute('select', lambda: self.selector.select(snapshot, limits, deadline))
            context = await execute('context', lambda: self.builder.build(snapshot, selection, limits, deadline,
                                                                        client.adapter.context_tokens))
            result['coverage'] = asdict(context.coverage)
            generation = await execute('generate', lambda: client.generate(GenerationRequest(
                context, snapshot.commit_sha, limits, deadline, payload['prompt_version'], payload['finding_schema_version'])))
            result['provenance']['usage'] = asdict(generation.usage)
            if (generation.commit_sha != snapshot.commit_sha or generation.context != context
                    or generation.prompt_version != payload['prompt_version']
                    or generation.finding_schema_version != payload['finding_schema_version']
                    or generation.provider != client.adapter.provider or generation.model != client.adapter.model):
                raise LLMError('invalid_result')
            validated = await execute('validate', lambda: self.validator.validate(generation.candidate_json, context, limits, deadline))
            result.update(outcome='succeeded', findings=list(validated.findings))
        except (AcquisitionError, SelectionError, ContextError, FindingError, LLMError) as error:
            if isinstance(error, AcquisitionError) and error.commit_sha is not None:
                result['commit_sha'] = error.commit_sha
            if isinstance(error, LLMError) and result['provenance'] is not None and stage == 'generate':
                result['provenance']['usage'] = asdict(error.usage)
            result['error'] = {'code': error.code, 'stage': stage, 'retryable': error.code in TRANSIENT}
        except TimeoutError:
            result['error'] = {'code': 'upstream_timeout', 'stage': stage, 'retryable': True}
        except Exception:
            # Never return exception messages, source, prompts or provider responses.
            result['error'] = {'code': 'invalid_result', 'stage': stage, 'retryable': False}
        finally:
            started = time.monotonic()
            if entered:
                # Shield cleanup on caller cancellation; keep the endpoint slot until
                # cleanup finishes. RepositoryReader independently bounds cleanup.
                task = asyncio.create_task(manager.__aexit__(None, None, None))
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
            result['stage_durations_ms']['cleanup'] = min(limits['cleanup_seconds'] * 1000,
                                                          int((time.monotonic() - started) * 1000))
        return (200 if result['outcome'] == 'succeeded' else status_for(result['error']['code'])), result
