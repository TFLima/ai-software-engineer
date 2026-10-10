export const id = '11111111-1111-4111-8111-111111111111';
export const sha = 'a'.repeat(40);
export function analysis(status = 'completed') {
  const completed = status === 'completed', failed = status === 'failed';
  return { schema_version: 1, id, status,
    repository: { owner: 'example', name: 'small-app', url: 'https://github.com/example/small-app' },
    commit_sha: completed ? sha : null, attempt_count: status === 'queued' ? 0 : 1,
    active_attempt_id: status === 'running' ? '22222222-2222-4222-8222-222222222222' : null,
    created_at: '2026-10-10T12:00:00Z', started_at: status === 'queued' ? null : '2026-10-10T12:00:01Z',
    finished_at: completed || failed ? '2026-10-10T12:00:10Z' : null,
    coverage: completed ? { inventory_files: 3, eligible_files: 2, included_files: 1, included_lines: 10, omitted_files: 2,
      omissions: [{ reason: 'sensitive', files: 1 }, { reason: 'context_budget', files: 1 }], limitations: ['Static inspection only'] } : null,
    provenance: completed ? { finding_schema_version: 1, selection_policy_version: '1', context_policy_version: '1', prompt_version: '1', provider: 'fake', model: 'fixture-v1', usage: { input_tokens: null, output_tokens: 100 } } : null,
    error: failed ? { code: 'configuration_error', stage: 'request', message: 'Analysis could not be completed.', retryable: false } : null };
}
export function finding(n = 1) {
  return { id: `33333333-3333-4333-8333-${String(n).padStart(12, '0')}`, category: 'security', severity: 'medium',
    title: `Achado ${n}`, explanation: '<img src=x onerror="window.xss=1">', recommendation: '<script>window.xss=2</script>',
    evidence: [{ path: 'app/a.php', start_line: 1, end_line: 10 }] };
}
export function findings(page = 1, total = 6) {
  return { schema_version: 1, analysis_id: id, commit_sha: sha, finding_schema_version: 1,
    data: Array.from({ length: Math.max(0, Math.min(5, total - (page - 1) * 5)) }, (_, i) => finding((page - 1) * 5 + i + 1)),
    pagination: { page, per_page: 5, total, total_pages: Math.ceil(total / 5) } };
}
export function apiError(code) { return { schema_version: 1, error: { code, message: 'Safe platform message.', details: [] } }; }
