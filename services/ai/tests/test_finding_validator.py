"""Strict candidate, exact source evidence and whole-response rejection fixtures."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.context_builder import ContextBuilder, IncludedSpan
from app.file_selector import FileSelector
from app.finding_validator import FindingError, FindingValidator
from app.limits import CEILINGS
from app.snapshot import ManifestEntry, Snapshot


def deadline(seconds=240):
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


@pytest.fixture
def context(tmp_path):
    (tmp_path / 'a.py').write_text('one\ntwo\nthree\n', encoding='utf-8')
    snapshot = Snapshot(tmp_path, 'a' * 40, (ManifestEntry('a.py', 14),), (), ())
    selection = FileSelector().select(snapshot, CEILINGS, deadline())
    return ContextBuilder().build(snapshot, selection, CEILINGS, deadline())


def candidate():
    return {'schema_version': 1, 'findings': [{
        'category': 'reliability', 'severity': 'medium', 'title': ' Potential concern ',
        'explanation': 'Static inspection suggests a risk.\nCheck the behavior.',
        'recommendation': ' Consider checking failure handling. ',
        'evidence': [{'path': 'a.py', 'start_line': 1, 'end_line': 3}]}]}


def validate(value, context, limits=None):
    return FindingValidator().validate(json.dumps(value), context, limits or CEILINGS, deadline())


def test_valid_trimmed_advisory_and_empty_with_real_b07_context(context):
    result = validate(candidate(), context)
    assert result.findings[0]['title'] == 'Potential concern'
    assert result.findings[0]['recommendation'] == 'Consider checking failure handling.'
    assert 'confidence' not in result.findings[0]
    assert result.coverage is context.coverage
    assert validate({'schema_version': 1, 'findings': []}, context).findings == ()


@pytest.mark.parametrize('raw', [
    '', '[]', '{}', 'null', '{', '```json\n{}\n```',
    '{"schema_version":1,"schema_version":1,"findings":[]}',
    '{"schema_version":1,"findings":[]} trailing',
    '{"schema_version":true,"findings":[]}',
    '{"schema_version":2,"findings":[]}',
    '{"schema_version":1,"findings":[],"tool_call":"execute"}',
    '{"schema_version":1,"findings":[NaN]}',
    '[' * 2000,
])
def test_bad_json_and_closed_root(raw, context):
    with pytest.raises(FindingError, match='invalid_findings'):
        FindingValidator().validate(raw, context, CEILINGS, deadline())


@pytest.mark.parametrize('key,value', [
    ('category', 'performance'), ('category', []), ('severity', 'urgent'),
    ('title', ''), ('title', ' '), ('title', 'x' * 161), ('title', 'a\nb'),
    ('title', 'a\tb'), ('explanation', 'x' * 4001), ('explanation', 'a\x00b'),
    ('recommendation', None), ('recommendation', 'x' * 2001),
    ('confidence', None), ('confidence', True), ('confidence', 1.1),
    ('confidence', float('inf')), ('confidence', float('nan')),
    ('evidence', []), ('tool_call', 'execute'),
])
def test_invalid_finding_rejects_whole_candidate(key, value, context):
    payload = candidate()
    invalid = deepcopy(payload['findings'][0])
    invalid[key] = value
    payload['findings'].append(invalid)
    with pytest.raises(FindingError, match='invalid_findings'):
        validate(payload, context)


@pytest.mark.parametrize('entry', [
    {'path': '../a.py', 'start_line': 1, 'end_line': 1},
    {'path': 'A.py', 'start_line': 1, 'end_line': 1},
    {'path': 'a.py', 'start_line': 0, 'end_line': 1},
    {'path': 'a.py', 'start_line': True, 'end_line': 1},
    {'path': 'a.py', 'start_line': 1.0, 'end_line': 1},
    {'path': 'a.py', 'start_line': 3, 'end_line': 2},
    {'path': 'a.py', 'start_line': 1, 'end_line': 4},
    {'path': 'a.py', 'start_line': 1, 'end_line': 1, 'excerpt': 'source'},
])
def test_bad_evidence(entry, context):
    payload = candidate()
    payload['findings'][0]['evidence'] = [entry]
    with pytest.raises(FindingError, match='invalid_findings'):
        validate(payload, context)


def test_duplicate_keys_nested_and_duplicate_evidence(context):
    raw = json.dumps(candidate()).replace('"path": "a.py"', '"path":"a.py","path":"a.py"')
    with pytest.raises(FindingError, match='invalid_findings'):
        FindingValidator().validate(raw, context, CEILINGS, deadline())
    payload = candidate()
    payload['findings'][0]['evidence'] *= 2
    with pytest.raises(FindingError, match='invalid_findings'):
        validate(payload, context)


def test_count_limits_and_exact_text_boundaries(context):
    payload = candidate()
    payload['findings'] *= 20
    assert len(validate(payload, context).findings) == 20
    payload['findings'].append(deepcopy(payload['findings'][0]))
    with pytest.raises(FindingError, match='invalid_findings'):
        validate(payload, context)
    payload = candidate()
    for key, size in [('title', 160), ('explanation', 4000), ('recommendation', 2000)]:
        payload['findings'][0][key] = 'é' * size
    payload['findings'][0]['confidence'] = 0
    assert validate(payload, context).findings[0]['confidence'] == 0
    with pytest.raises(FindingError, match='invalid_request'):
        validate(payload, context, {**CEILINGS, 'path_characters': 3})
    payload['findings'] *= 2
    with pytest.raises(FindingError, match='invalid_findings'):
        validate(payload, context, {**CEILINGS, 'max_findings': 1})


def test_disjoint_spans_cannot_cross_gap_and_adjacent_spans_can(context):
    coverage = replace(context.coverage, included_lines=2,
                       included_spans=(IncludedSpan('a.py', 1, 1), IncludedSpan('a.py', 3, 3)))
    with pytest.raises(FindingError, match='invalid_findings'):
        validate(candidate(), replace(context, coverage=coverage))
    coverage = replace(context.coverage,
                       included_spans=(IncludedSpan('a.py', 1, 1), IncludedSpan('a.py', 2, 3)))
    assert validate(candidate(), replace(context, coverage=coverage)).findings


def test_empty_requires_context_and_expired_deadline(context):
    with pytest.raises(FindingError, match='no_eligible_context'):
        validate({'schema_version': 1, 'findings': []}, replace(context, text=''))
    with pytest.raises(FindingError, match='limit_exceeded'):
        FindingValidator().validate(json.dumps(candidate()), context, CEILINGS, deadline(0))
    raw = json.dumps(candidate())
    with pytest.raises(FindingError, match='limit_exceeded'):
        FindingValidator().validate(raw, context, {**CEILINGS, 'internal_response_bytes': 1}, deadline())


def test_markup_remains_plain_text_and_unicode_identity_is_exact(context):
    payload = candidate()
    payload['findings'][0]['title'] = '<script>alert(1)</script>'
    assert validate(payload, context).findings[0]['title'] == '<script>alert(1)</script>'
    coverage = replace(context.coverage, included_spans=(IncludedSpan('é.py', 1, 3),))
    payload['findings'][0]['evidence'][0]['path'] = 'e\u0301.py'
    with pytest.raises(FindingError, match='invalid_findings'):
        validate(payload, replace(context, coverage=coverage))


@pytest.mark.parametrize('path', ['/a.py', 'a.py/', 'a//b', './a.py', 'a/../b',
                                  'a\\b', 'C:a.py', 'a\x00b', 'a\u007fb',
                                  'a/' * 12 + 'b', 'a' * 513])
def test_unsafe_paths(path, context):
    payload = candidate()
    payload['findings'][0]['evidence'][0]['path'] = path
    with pytest.raises(FindingError, match='invalid_findings'):
        validate(payload, context)


def test_evidence_count_boundary(context):
    coverage = replace(context.coverage, included_lines=5,
                       included_spans=(IncludedSpan('a.py', 1, 5),))
    payload = candidate()
    payload['findings'][0]['evidence'] = [
        {'path': 'a.py', 'start_line': n, 'end_line': n} for n in range(1, 6)]
    assert validate(payload, replace(context, coverage=coverage)).findings
    with pytest.raises(FindingError, match='invalid_findings'):
        validate(payload, replace(context, coverage=coverage), {**CEILINGS, 'evidence_per_finding': 4})


def test_forged_coverage_counts_and_overlap_fail(context):
    for coverage in [replace(context.coverage, included_lines=4),
                     replace(context.coverage, included_files=True),
                     replace(context.coverage, included_spans=(IncludedSpan('a.py', 1, 2),
                                                              IncludedSpan('a.py', 2, 3)))]:
        with pytest.raises(FindingError, match='invalid_request'):
            validate(candidate(), replace(context, coverage=coverage))
