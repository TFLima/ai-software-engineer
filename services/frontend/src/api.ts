/** Closed v1 public contracts. No source, credentials or internal evidence map. */
export type Status = 'queued' | 'running' | 'completed' | 'failed';
export interface Submission { schema_version: 1; id: string; status: Status; }
export interface Evidence { path: string; start_line: number; end_line: number; }
export interface Finding {
  id: string; category: string; severity: string; title: string;
  explanation: string; recommendation: string; evidence: Evidence[]; confidence?: number;
}
export interface Coverage {
  inventory_files: number; eligible_files: number; included_files: number;
  included_lines: number; omitted_files: number;
  omissions: { reason: string; files: number }[]; limitations: string[];
}
export interface Analysis extends Submission {
  repository: { owner: string; name: string; url: string }; commit_sha: string | null;
  attempt_count: number; active_attempt_id: string | null;
  created_at: string; started_at: string | null; finished_at: string | null;
  coverage: Coverage | null;
  provenance: null | { finding_schema_version: 1; selection_policy_version: '1';
    context_policy_version: '1'; prompt_version: '1'; provider: string; model: string;
    usage: { input_tokens: number | null; output_tokens: number | null } };
  error: null | { code: string; stage: string; message: string; retryable: boolean };
}
export interface FindingsPage {
  schema_version: 1; analysis_id: string; commit_sha: string; finding_schema_version: 1;
  data: Finding[]; pagination: { page: number; per_page: number; total: number; total_pages: number };
}
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA = /^[0-9a-f]{40}$/;
const statuses = ['queued', 'running', 'completed', 'failed'];
const categories = ['architecture', 'maintainability', 'reliability', 'security', 'testing'];
const severities = ['info', 'low', 'medium', 'high', 'critical'];
const reasons = ['binary', 'generated', 'vendor', 'sensitive', 'unsupported_text', 'context_budget', 'submodule', 'lfs'];
const transient = ['network_unavailable', 'upstream_timeout', 'upstream_rate_limited', 'upstream_unavailable', 'attempt_expired', 'queue_unavailable'];
const terminal = ['invalid_request', 'unsupported_schema', 'unauthorized_internal', 'repository_unavailable', 'unsafe_snapshot', 'limit_exceeded', 'no_eligible_context', 'invalid_findings', 'invalid_result', 'configuration_error'];
const stages = ['request', 'acquire', 'select', 'context', 'generate', 'validate', 'cleanup', 'transport', 'queue'];
function requireValue(value: unknown): asserts value { if (!value) throw new Error('Invalid public response'); }
function object(value: any, keys: string[], optional: string[] = []): void {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value));
  requireValue(keys.every(k => Object.hasOwn(value, k)) && Object.keys(value).every(k => [...keys, ...optional].includes(k)));
}
function integer(value: any, min = 0, max = Number.MAX_SAFE_INTEGER): void {
  requireValue(Number.isSafeInteger(value) && value >= min && value <= max);
}
function text(value: any, max: number, multiline = true): void {
  requireValue(typeof value === 'string' && [...value.trim()].length > 0 && [...value.trim()].length <= max);
  requireValue(!(multiline ? /[\p{Cc}\p{Cs}]/u.test(value.replace(/[\n\t]/g, '')) : /[\p{Cc}\p{Cs}]/u.test(value)));
}
function timestamp(value: any, nullable = true): void {
  requireValue((nullable && value === null) || (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value) && Number.isFinite(Date.parse(value))));
}
export function canonicalRepository(value: string): string | null {
  if (value.length > 2048 || /\s/.test(value) || !value.startsWith('https://')) return null;
  const match = /^https:\/\/github\.com\/([^/]+)\/([^/]+)\/?$/i.exec(value);
  if (!match) return null;
  const owner = match[1], name = match[2].replace(/\.git$/i, '');
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(owner) || owner.includes('--') ||
      !/^[A-Za-z0-9._-]{1,100}$/.test(name) || ['.', '..'].includes(name)) return null;
  return `https://github.com/${owner.toLowerCase()}/${name.toLowerCase()}`;
}
/** Reject duplicate keys before JSON.parse, including nested objects. */
export function strictJson(source: string): any {
  requireValue(new TextEncoder().encode(source).length <= 1048576);
  let at = 0;
  function space() { while (/\s/.test(source[at] ?? '') && at < source.length) at++; }
  function string(): string {
    const start = at++;
    while (at < source.length) {
      const character = source[at++];
      if (character === '\\') at++;
      else if (character === '"') return JSON.parse(source.slice(start, at));
    }
    throw new Error('Invalid public response');
  }
  function value(depth: number): void {
    requireValue(depth < 32); space();
    const char = source[at];
    if (char === '"') { string(); return; }
    if (char === '{' || char === '[') {
      const end = char === '{' ? '}' : ']'; const keys = new Set<string>(); at++; space();
      if (source[at] === end) { at++; return; }
      while (at < source.length) {
        if (char === '{') {
          requireValue(source[at] === '"'); const key = string();
          requireValue(!keys.has(key)); keys.add(key); space(); requireValue(source[at++] === ':');
        }
        value(depth + 1); space();
        if (source[at] === end) { at++; return; }
        requireValue(source[at++] === ','); space();
      }
      throw new Error('Invalid public response');
    }
    const token = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(source.slice(at));
    requireValue(token); at += token[0].length;
    if (!['true', 'false', 'null'].includes(token[0])) requireValue(Number.isFinite(Number(token[0])));
  }
  value(0); space(); requireValue(at === source.length); return JSON.parse(source);
}
export function decodeSubmission(source: string): Submission {
  const value = strictJson(source); object(value, ['schema_version', 'id', 'status']);
  requireValue(value.schema_version === 1 && UUID.test(value.id) && statuses.includes(value.status));
  return value;
}
export function decodeAnalysis(source: string, id: string): Analysis {
  const v = strictJson(source);
  object(v, ['schema_version', 'id', 'status', 'repository', 'commit_sha', 'attempt_count', 'active_attempt_id', 'created_at', 'started_at', 'finished_at', 'coverage', 'provenance', 'error']);
  requireValue(v.schema_version === 1 && v.id === id && UUID.test(v.id) && statuses.includes(v.status));
  object(v.repository, ['owner', 'name', 'url']);
  requireValue(canonicalRepository(v.repository.url) === v.repository.url && v.repository.url === `https://github.com/${v.repository.owner}/${v.repository.name}`);
  requireValue(v.commit_sha === null || (typeof v.commit_sha === 'string' && SHA.test(v.commit_sha)));
  integer(v.attempt_count, 0, 3);
  requireValue(v.status === 'running' ? UUID.test(v.active_attempt_id) : v.active_attempt_id === null);
  timestamp(v.created_at, false); timestamp(v.started_at); timestamp(v.finished_at);
  if (v.coverage !== null) {
    const c = v.coverage; object(c, ['inventory_files', 'eligible_files', 'included_files', 'included_lines', 'omitted_files', 'omissions', 'limitations']);
    for (const k of ['inventory_files', 'eligible_files', 'included_files', 'omitted_files']) integer(c[k], 0, 2000);
    integer(c.included_lines); requireValue(c.included_files <= c.eligible_files && c.eligible_files <= c.inventory_files && c.omitted_files === c.inventory_files - c.included_files && c.included_files <= 100);
    requireValue(Array.isArray(c.omissions) && c.omissions.length <= 16);
    const seen = new Set(); let omitted = 0;
    for (const omission of c.omissions) { object(omission, ['reason', 'files']); requireValue(reasons.includes(omission.reason) && !seen.has(omission.reason)); seen.add(omission.reason); integer(omission.files, 0, 2000); omitted += omission.files; }
    requireValue(omitted === c.omitted_files && Array.isArray(c.limitations) && c.limitations.length >= 1 && c.limitations.length <= 16);
    c.limitations.forEach((s: any) => text(s, 256));
  }
  if (v.provenance !== null) {
    const p = v.provenance; object(p, ['finding_schema_version', 'selection_policy_version', 'context_policy_version', 'prompt_version', 'provider', 'model', 'usage']);
    requireValue(p.finding_schema_version === 1 && p.selection_policy_version === '1' && p.context_policy_version === '1' && p.prompt_version === '1');
    text(p.provider, 128, false); text(p.model, 128, false); object(p.usage, ['input_tokens', 'output_tokens']);
    if (p.usage.input_tokens !== null) integer(p.usage.input_tokens, 0, 32000);
    if (p.usage.output_tokens !== null) integer(p.usage.output_tokens, 0, 12000);
  }
  if (v.error !== null) {
    object(v.error, ['code', 'stage', 'message', 'retryable']);
    requireValue([...transient, ...terminal].includes(v.error.code) && stages.includes(v.error.stage) && v.error.retryable === transient.includes(v.error.code)); text(v.error.message, 256);
  }
  if (v.status === 'completed') requireValue(v.commit_sha && v.coverage?.included_files > 0 && v.coverage.included_lines > 0 && v.provenance && v.error === null);
  if (v.status === 'failed') requireValue(v.error !== null);
  return v;
}
export function decodeFindings(source: string, id: string, sha: string, page: number, perPage: number): FindingsPage {
  const v = strictJson(source); object(v, ['schema_version', 'analysis_id', 'commit_sha', 'finding_schema_version', 'data', 'pagination']);
  requireValue(v.schema_version === 1 && v.finding_schema_version === 1 && v.analysis_id === id && v.commit_sha === sha && SHA.test(sha));
  object(v.pagination, ['page', 'per_page', 'total', 'total_pages']);
  const p = v.pagination; integer(p.page, 1, 2147483647); integer(p.per_page, 1, 20); integer(p.total, 0, 20); integer(p.total_pages, 0, 20);
  requireValue(p.page === page && p.per_page === perPage && p.total_pages === Math.ceil(p.total / p.per_page) && Array.isArray(v.data) && v.data.length === Math.max(0, Math.min(p.per_page, p.total - (p.page - 1) * p.per_page)));
  const ids = new Set();
  for (const f of v.data) {
    object(f, ['id', 'category', 'severity', 'title', 'explanation', 'recommendation', 'evidence'], ['confidence']);
    requireValue(UUID.test(f.id) && !ids.has(f.id) && categories.includes(f.category) && severities.includes(f.severity)); ids.add(f.id);
    text(f.title, 160, false); text(f.explanation, 4000); text(f.recommendation, 2000);
    if (Object.hasOwn(f, 'confidence')) requireValue(typeof f.confidence === 'number' && Number.isFinite(f.confidence) && f.confidence >= 0 && f.confidence <= 1);
    requireValue(Array.isArray(f.evidence) && f.evidence.length >= 1 && f.evidence.length <= 5);
    const seen = new Set();
    for (const e of f.evidence) {
      object(e, ['path', 'start_line', 'end_line']); text(e.path, 512, false);
      requireValue(!/[\\\p{Cc}\p{Cf}\p{Cs}]/u.test(e.path) && !/^[A-Za-z]:/.test(e.path) && e.path.split('/').length <= 12 && e.path.split('/').every((s: string) => !['', '.', '..'].includes(s)));
      integer(e.start_line, 1); integer(e.end_line, e.start_line); const identity = JSON.stringify(e); requireValue(!seen.has(identity)); seen.add(identity);
    }
  }
  return v;
}
export function publicErrorCode(source: string): string {
  const v = strictJson(source); object(v, ['schema_version', 'error']); object(v.error, ['code', 'message', 'details']);
  requireValue(v.schema_version === 1 && typeof v.error.code === 'string'); text(v.error.message, 256);
  requireValue(Array.isArray(v.error.details));
  for (const detail of v.error.details) { object(detail, ['field', 'code']); text(detail.field, 128, false); requireValue(['required', 'invalid_type', 'invalid_repository_url', 'invalid_idempotency_key', 'unknown_field', 'out_of_range'].includes(detail.code)); }
  return v.error.code;
}
