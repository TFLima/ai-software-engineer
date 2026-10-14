#!/usr/bin/env python3
"""B13 isolated full-stack acceptance. No real source/provider network calls.

Requires Docker Compose, frontend dev dependencies and Playwright Chromium.
Creates its own project, generated secrets and test DB; always attempts cleanup.
Never uses an existing dev project's database or prints expanded environment.
"""
import base64
import importlib.util
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent


def main():
    for binary in ('docker', 'npm'):
        if shutil.which(binary) is None:
            raise RuntimeError(f'Missing prerequisite: {binary}')
    if not (ROOT / 'services/frontend/node_modules/playwright').is_dir():
        raise RuntimeError('Run npm ci and npx playwright install chromium --only-shell in services/frontend')
    # Fail before creating anything if the documented loopback edge port is in use.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8080))
    project = 'ase-b13-' + uuid.uuid4().hex[:12]
    env = {**os.environ, 'APP_KEY': 'base64:' + base64.b64encode(secrets.token_bytes(32)).decode(),
           'DB_PASSWORD': secrets.token_hex(32), 'AI_INTERNAL_SECRET': secrets.token_hex(32),
           'LLM_REAL_ENABLED': 'false', 'OPENAI_API_KEY': '', 'B13_ACCEPTANCE': '1'}
    compose = ['docker', 'compose', '--project-name', project,
               '-f', 'compose.yaml', '-f', 'compose.acceptance.yaml']

    def run(label, args, cwd=ROOT):
        print(f'CHECK {label}', flush=True)
        result = subprocess.run(args, cwd=cwd, env=env, check=False)
        if result.returncode:
            raise RuntimeError(f'{label} failed (exit {result.returncode})')

    subprocess.run(['docker', 'compose', 'version'], env=env, check=True)
    try:
        run('configuration', compose + ['config', '--quiet'])
        run('build', compose + ['build', 'api', 'ai', 'frontend'])
        run('test dependencies', compose + ['up', '-d', '--wait', '--wait-timeout', '180', 'postgres', 'redis'])
        # No API/worker/scheduler is running while RefreshDatabase owns the test DB.
        run('Laravel PostgreSQL regressions', compose + ['run', '--rm', '--no-deps', 'api', 'composer', 'test'])
        run('migrations', compose + ['run', '--rm', '--no-deps', 'api', 'php', 'artisan', 'migrate', '--force'])
        run('full test stack', compose + ['up', '-d', '--wait', '--wait-timeout', '180'])
        spec = importlib.util.spec_from_file_location('stack_verification', ROOT / 'scripts/verify-stack.py')
        verification = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verification)
        verification.compose = lambda *args: subprocess.check_output(
            compose + list(args), cwd=ROOT, env=env, text=True).strip()
        verification.main(database="ai_software_engineer_test")
        run('real browser flow', ['npm', 'run', 'test:integrated'], ROOT / 'services/frontend')
        run('operator inspection commands', compose + ['exec', '-T', 'scheduler', 'php', 'artisan', 'analyses:purge'])
    finally:
        # The random project owns these volumes; never targets a dev project.
        result = subprocess.run(compose + ['down', '--volumes', '--remove-orphans'], cwd=ROOT, env=env)
        if result.returncode:
            raise RuntimeError(f'Cleanup failed for disposable project {project}')
    print('PASS B13 full stack: persisted public snapshot, malformed output and escaped XSS; fake acquisition/provider only', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError, AssertionError) as error:
        # Do not include subprocess environment or any generated credentials.
        print(f'FAIL {error}', file=sys.stderr)
        sys.exit(1)
