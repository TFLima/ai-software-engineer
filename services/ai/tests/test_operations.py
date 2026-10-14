import json
import os
from unittest.mock import patch

import pytest
from app.operations import CORRELATION, STALE_SECONDS, cleanup_stale, event


def test_cleanup_preserves_fresh_unrelated_and_symlink_targets(tmp_path):
    old = tmp_path / 'ase-snapshot-abcdefgh'
    old.mkdir()
    (old / 'source').write_text('private source')
    os.utime(old, (1, 1))
    fresh = tmp_path / 'ase-snapshot-12345678'
    fresh.mkdir()
    unrelated = tmp_path / 'operator-data'
    unrelated.mkdir()
    os.utime(unrelated, (1, 1))
    link = tmp_path / 'ase-snapshot-87654321'
    link.symlink_to(unrelated, target_is_directory=True)
    (old / 'link').symlink_to(unrelated, target_is_directory=True)
    os.utime(old, (1, 1))
    assert cleanup_stale(tmp_path, now=STALE_SECONDS + 2) == (1, 0)
    assert not old.exists()
    assert fresh.exists() and unrelated.exists() and link.is_symlink()


def test_cleanup_rejects_link_root(tmp_path):
    link = tmp_path / 'root'
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError):
        cleanup_stale(link)


def test_cleanup_failure_is_safe_and_correlated(tmp_path, caplog):
    old = tmp_path / 'ase-snapshot-abcdefgh'
    old.mkdir()
    os.utime(old, (1, 1))
    token = CORRELATION.set({'analysis_id': 'a', 'attempt_id': 'b'})
    try:
        with patch('app.operations.shutil.rmtree', side_effect=OSError('SECRET SOURCE')):
            assert cleanup_stale(tmp_path, now=STALE_SECONDS + 2) == (0, 1)
    finally:
        CORRELATION.reset(token)
    record = json.loads(caplog.records[-1].message)
    assert record['analysis_id'] == 'a' and record['attempt_id'] == 'b'
    assert record['failed'] == 1 and 'SECRET SOURCE' not in caplog.text


def test_events_exclude_arbitrary_fields(caplog):
    event('fixture', analysis_id='a', usage={'input_tokens': None, 'output_tokens': 3},
          source='SOURCE', prompt='PROMPT', secret='SECRET', provider_output='RAW')
    message = json.loads(caplog.records[-1].message)
    assert set(message) == {'event', 'analysis_id', 'usage'}


def test_cleanup_deletion_batch_is_bounded(tmp_path):
    for index in range(101):
        path = tmp_path / f'ase-snapshot-{index:08d}'
        path.mkdir()
        os.utime(path, (1, 1))
    assert cleanup_stale(tmp_path, now=STALE_SECONDS + 2) == (100, 0)
    assert len(list(tmp_path.iterdir())) == 1


def test_sweeper_waits_for_active_analysis_slot(monkeypatch, tmp_path):
    import asyncio
    from app.main import app, lifespan
    calls = []
    monkeypatch.setenv('AI_INTERNAL_SECRET', 's' * 64)
    monkeypatch.setattr('app.main.workspace_root', lambda: tmp_path)
    monkeypatch.setattr('app.main.cleanup_stale', lambda: calls.append('swept'))

    async def scenario():
        async with lifespan(app):
            await app.state.slot.acquire()
            try:
                await asyncio.sleep(0)
                assert calls == []
            finally:
                app.state.slot.release()
            for _ in range(100):
                await asyncio.sleep(0.001)
                if calls:
                    break
            assert calls == ['swept']
    asyncio.run(scenario())
