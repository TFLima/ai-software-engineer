#!/usr/bin/env python3
"""Opt-in paid comparison at one public repository and immutable SHA; no DB writes."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services' / 'ai'))
from app.llm_factory import llm_client_from_env
from app.limits import CEILINGS
from app.main import validate
from app.orchestrator import AnalysisOrchestrator


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--allow-paid', action='store_true', help='Authorize two paid runs including bounded retries')
    args = parser.parse_args()
    if not args.allow_paid:
        parser.error('Paid comparison requires explicit --allow-paid authorization')
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        parser.error('Expected immutable lowercase SHA')
    return args


async def compare(args):
    # Validate both provider configurations before any acquisition or paid call.
    clients = {p: llm_client_from_env({**os.environ, 'LLM_PROVIDER': p})
               for p in ('openai', 'anthropic')}
    reports = []
    for provider, client in clients.items():
        payload = validate({
            'schema_version': 1, 'finding_schema_version': 1,
            'analysis_id': str(uuid4()), 'attempt_id': str(uuid4()), 'attempt_number': 1,
            'repository': {'owner': args.repository.split('/')[-2],
                           'name': args.repository.split('/')[-1], 'url': args.repository},
            'commit_sha': args.commit,
            'deadline_at': (datetime.now(timezone.utc) + timedelta(seconds=239)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'selection_policy_version': '1', 'context_policy_version': '1', 'prompt_version': '1',
            'limits': dict(CEILINGS)})
        started = time.monotonic()
        status, result = await AnalysisOrchestrator(client_factory=lambda: client).run(payload)
        usage = (result.get('provenance') or {}).get('usage', {})
        inp, out = usage.get('input_tokens'), usage.get('output_tokens')
        reports.append({
            'provider': provider, 'model': client.adapter.model, 'repository': args.repository,
            'commit_sha': result['commit_sha'], 'usage': usage,
            'estimated_cost_microusd': client.cost.reserve(inp, out) if inp is not None and out is not None else None,
            'attempt_budget_microusd': client.cost.attempt_microusd,
            'elapsed_ms': int((time.monotonic() - started) * 1000),
            'outcome': result['outcome'], 'http_status': status, 'error': result.get('error'),
            'finding_count': len(result.get('findings', [])),
            'structural_evidence_validation_passed': result['outcome'] == 'succeeded',
            'semantic_evidence_review': 'pending manual review',
            'false_positive_review': 'pending manual review',
            'limitations': ['Schema/line-span checks do not establish finding quality.',
                            'Configured-rate cost estimate is not provider billing; unknown usage is not zero.',
                            'Same SHA acquired independently; no findings/source stored in this report.']})
    args.output.write_text(json.dumps({'schema_version': 1, 'runs': reports}, indent=2) + '\n')
    print(f'Report written to {args.output}')


if __name__ == '__main__':
    try:
        asyncio.run(compare(arguments()))
    except Exception:
        print('Comparison failed; check required configuration and canonical repository identity.', file=sys.stderr)
        sys.exit(1)
