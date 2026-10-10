import { test } from 'node:test';
import assert from 'node:assert/strict';
import { canonicalRepository, strictJson, decodeSubmission, decodeAnalysis, decodeFindings, publicErrorCode } from '../src/api.ts';
import { id, sha, analysis, findings, apiError } from './fixtures.mjs';

test('canonical public URLs and rejected source-controlled endpoints', () => {
  assert.equal(canonicalRepository('https://GitHub.com/Example/Small-App.git/'), 'https://github.com/example/small-app');
  for (const url of ['http://github.com/a/b', 'https://github.com:443/a/b', 'https://a@github.com/a/b', 'https://github.com/a/b/tree/main', 'https://github.com/a/b?x=1', 'https://github.com/a/b#main', 'https://github.com/a/%62', 'https://github.com/a--b/c', 'https://github.com/a/..', 'https://github.com/a/b\n', 'https://127.0.0.1/a/b']) assert.equal(canonicalRepository(url), null, url);
});
test('strict JSON rejects duplicate and escaped duplicate keys, nonfinite numbers and deep nesting', () => {
  for (const body of ['{"a":1,"a":2}', '{"x":{"a":1,"\\u0061":2}}', '{"x":NaN}', '{"x":1e999}', '{} trailing', '['.repeat(33) + '0' + ']'.repeat(33), '"unterminated', '[1,]', '{"a":1,}']) assert.throws(() => strictJson(body));
  assert.deepEqual(strictJson('{"a":"escaped \\" quote", "b":[1,true,null]}'), { a: 'escaped " quote', b: [1,true,null] });
});
test('submission and four analysis states follow exact v1 contracts', () => {
  assert.equal(decodeSubmission(JSON.stringify({ schema_version: 1, id, status: 'queued' })).id, id);
  for (const status of ['queued', 'running', 'completed', 'failed']) assert.equal(decodeAnalysis(JSON.stringify(analysis(status)), id).status, status);
  for (const mutate of [v => v.extra = 1, v => v.schema_version = 2, v => v.id = 'wrong', v => v.coverage.included_spans = [], v => v.coverage.omitted_files = 0, v => v.provenance.prompt_version = '2', v => v.error = { code: 'upstream_unavailable', stage: 'generate', message: 'safe', retryable: false }]) { const v = analysis(); mutate(v); assert.throws(() => decodeAnalysis(JSON.stringify(v), id)); }
});
test('findings enforce SHA, pagination, nested fields and bounded evidence without interpreting HTML', () => {
  const valid = findings(); assert.equal(decodeFindings(JSON.stringify(valid), id, sha, 1, 5).data[0].explanation, valid.data[0].explanation);
  assert.equal(decodeFindings(JSON.stringify(findings(1, 0)), id, sha, 1, 5).data.length, 0);
  for (const mutate of [v => v.commit_sha = 'b'.repeat(40), v => v.finding_schema_version = 2, v => v.pagination.page = 2, v => v.data[0].extra = 'unknown', v => v.data[0].confidence = null, v => v.data[0].evidence[0].path = '../secret', v => v.data[0].evidence[0].start_line = true, v => v.data[0].evidence.push(v.data[0].evidence[0]), v => v.data[1].id = v.data[0].id]) { const v = findings(); mutate(v); assert.throws(() => decodeFindings(JSON.stringify(v), id, sha, 1, 5)); }
});
test('safe public errors reject unexpected metadata', () => {
  assert.equal(publicErrorCode(JSON.stringify(apiError('admission_limited'))), 'admission_limited');
  const value = apiError('internal_error'); value.error.stack = 'private'; assert.throws(() => publicErrorCode(JSON.stringify(value)));
});
