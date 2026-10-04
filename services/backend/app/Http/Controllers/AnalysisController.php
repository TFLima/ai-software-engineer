<?php

namespace App\Http\Controllers;

use App\Support\StrictJson;
use Illuminate\Database\QueryException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

final class AnalysisController
{
    public function store(Request $request): JsonResponse
    {
        if (strlen($request->getContent()) > 4096) {
            return self::error(413, 'request_too_large', 'Request body is too large.');
        }
        if ($request->header('Content-Type') !== 'application/json') {
            return self::error(415, 'unsupported_media_type', 'Content type must be application/json.');
        }
        if (!in_array('application/json', array_map(fn ($part) => trim(explode(';', $part)[0]), explode(',', $request->header('Accept', ''))), true)) {
            return self::error(422, 'validation_failed', 'Request validation failed.', [['field' => 'Accept', 'code' => 'invalid_type']]);
        }
        try {
            $body = StrictJson::decodeObject($request->getContent());
        } catch (\DomainException) {
            return self::error(422, 'validation_failed', 'Request validation failed.', [['field' => 'body', 'code' => 'invalid_type']]);
        }
        if ($body === null) {
            return self::error(400, 'invalid_json', 'Invalid JSON request.');
        }
        $details = [];
        $repository = null;
        if (!array_key_exists('repository_url', $body)) {
            $details[] = ['field' => 'repository_url', 'code' => 'required'];
        } elseif (!is_string($body['repository_url'])) {
            $details[] = ['field' => 'repository_url', 'code' => 'invalid_type'];
        } elseif (mb_strlen($body['repository_url']) > 2048 || ($repository = self::repository($body['repository_url'])) === null) {
            $details[] = ['field' => 'repository_url', 'code' => 'invalid_repository_url'];
        }
        foreach (array_keys($body) as $field) {
            if ($field !== 'repository_url') {
                $details[] = ['field' => $field, 'code' => 'unknown_field'];
            }
        }
        $key = $request->header('Idempotency-Key');
        if (!is_string($key) || !preg_match('/\A[A-Za-z0-9._:-]{1,128}\z/D', $key)) {
            $details[] = ['field' => 'Idempotency-Key', 'code' => 'invalid_idempotency_key'];
        }
        if ($details !== []) {
            return self::error(422, 'validation_failed', 'Request validation failed.', $details);
        }

        $hash = hash('sha256', json_encode(['repository_url' => $repository['url']], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));
        try {
            $result = DB::transaction(function () use ($key, $hash, $repository): array {
                // Serialize global admission and same-key replay on PostgreSQL.
                DB::select('SELECT pg_advisory_xact_lock(20261003, 3)');
                $existing = DB::table('analyses')->where('idempotency_key', $key)->first();
                if ($existing !== null) {
                    return $existing->request_hash === $hash
                        ? ['id' => $existing->id, 'status' => $existing->status]
                        : ['error' => 'idempotency_conflict'];
                }
                $now = Carbon::now('UTC');
                $recent = DB::table('analyses')->where('created_at', '>=', $now->copy()->subMinute())->count();
                $pending = DB::table('analyses')->whereIn('status', ['queued', 'running'])->count();
                if ($recent >= 6 || $pending >= 10) {
                    return ['error' => 'admission_limited'];
                }
                $id = (string) Str::uuid();
                DB::table('analyses')->insert([
                    'id' => $id,
                    'idempotency_key' => $key,
                    'request_hash' => $hash,
                    'repository_owner' => $repository['owner'],
                    'repository_name' => $repository['name'],
                    'repository_url' => $repository['url'],
                    'status' => 'queued',
                    'attempt_count' => 0,
                    'created_at' => $now,
                    'updated_at' => $now,
                ]);
                // The durable queued row is B03's publication intent. B04 adds delivery/reconciliation.
                return ['id' => $id, 'status' => 'queued'];
            });
        } catch (QueryException) {
            return self::error(503, 'application_unavailable', 'Application is temporarily unavailable.', [], 30);
        }
        if (isset($result['error'])) {
            return $result['error'] === 'idempotency_conflict'
                ? self::error(409, 'idempotency_conflict', 'Idempotency key is already bound to another request.')
                : self::error(429, 'admission_limited', 'Admission limit reached.', [], 60);
        }
        return response()->json(['schema_version' => 1, ...$result], 202)
            ->header('Location', '/api/analyses/'.$result['id']);
    }

    public function show(string $id): JsonResponse
    {
        $row = $this->find($id);
        if ($row instanceof JsonResponse) {
            return $row;
        }
        $coverage = self::jsonColumn($row->coverage);
        if ($coverage !== null) {
            unset($coverage['included_spans']);
        }
        $error = null;
        if ($row->error_code !== null) {
            $error = [
                'code' => $row->error_code,
                'stage' => $row->error_stage,
                'message' => 'Analysis could not be completed.',
                'retryable' => in_array($row->error_code, ['network_unavailable', 'upstream_timeout', 'upstream_rate_limited', 'upstream_unavailable', 'attempt_expired', 'queue_unavailable'], true),
            ];
        }
        return response()->json([
            'schema_version' => 1,
            'id' => $row->id,
            'status' => $row->status,
            'repository' => ['owner' => $row->repository_owner, 'name' => $row->repository_name, 'url' => $row->repository_url],
            'commit_sha' => $row->commit_sha,
            'attempt_count' => $row->attempt_count,
            'active_attempt_id' => $row->active_attempt_id,
            'created_at' => self::timestamp($row->created_at),
            'started_at' => self::timestamp($row->started_at),
            'finished_at' => self::timestamp($row->finished_at),
            'coverage' => $coverage,
            'provenance' => self::jsonColumn($row->provenance),
            'error' => $error,
        ]);
    }

    public function findings(Request $request, string $id): JsonResponse
    {
        $row = $this->find($id);
        if ($row instanceof JsonResponse) {
            return $row;
        }
        $details = [];
        $query = $request->query();
        foreach ($query as $field => $value) {
            if (!in_array($field, ['page', 'per_page'], true)) {
                $details[] = ['field' => $field, 'code' => 'unknown_field'];
            } elseif (!is_string($value) || !preg_match('/\A[1-9][0-9]*\z/D', $value) || (int) $value > ($field === 'page' ? 2147483647 : 20)) {
                $details[] = ['field' => $field, 'code' => 'out_of_range'];
            }
        }
        if ($details !== []) {
            return self::error(422, 'validation_failed', 'Request validation failed.', $details);
        }
        if ($row->status !== 'completed') {
            return self::error(409, 'analysis_not_completed', 'Analysis is not completed.');
        }
        $page = isset($query['page']) ? (int) $query['page'] : 1;
        $perPage = isset($query['per_page']) ? (int) $query['per_page'] : 20;
        try {
            $total = DB::table('findings')->where('analysis_id', $id)->count();
            $rows = DB::table('findings')->where('analysis_id', $id)
                ->orderBy('ordinal')->offset(($page - 1) * $perPage)->limit($perPage)->get();
        } catch (QueryException) {
            return self::error(503, 'application_unavailable', 'Application is temporarily unavailable.', [], 30);
        }
        $data = $rows->map(function ($finding): array {
            $item = [
                'id' => $finding->id,
                'category' => $finding->category,
                'severity' => $finding->severity,
                'title' => $finding->title,
                'explanation' => $finding->explanation,
                'recommendation' => $finding->recommendation,
                'evidence' => self::jsonColumn($finding->evidence),
            ];
            if ($finding->confidence !== null) {
                $item['confidence'] = (float) $finding->confidence;
            }
            return $item;
        })->all();
        return response()->json([
            'schema_version' => 1,
            'analysis_id' => $id,
            'commit_sha' => $row->commit_sha,
            'finding_schema_version' => 1,
            'data' => $data,
            'pagination' => ['page' => $page, 'per_page' => $perPage, 'total' => $total, 'total_pages' => $total === 0 ? 0 : (int) ceil($total / $perPage)],
        ]);
    }

    private function find(string $id): \stdClass|JsonResponse
    {
        if (!preg_match('/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/D', $id)) {
            return self::error(404, 'analysis_not_found', 'Analysis not found.');
        }
        try {
            $row = DB::table('analyses')->where('id', $id)->first();
        } catch (QueryException) {
            return self::error(503, 'application_unavailable', 'Application is temporarily unavailable.', [], 30);
        }
        return $row ?? self::error(404, 'analysis_not_found', 'Analysis not found.');
    }

    private static function repository(string $url): ?array
    {
        if (!str_starts_with($url, 'https://') || !preg_match('/\Ahttps:\/\/github\.com\/([^\/]+)\/([^\/]+)\/?\z/iD', $url, $parts)) {
            return null;
        }
        $owner = $parts[1];
        $name = preg_replace('/\.git\z/iD', '', $parts[2]);
        if (!preg_match('/\A[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\z/D', $owner)
            || str_contains($owner, '--')
            || !preg_match('/\A[A-Za-z0-9._-]{1,100}\z/D', $name)
            || in_array($name, ['.', '..'], true)) {
            return null;
        }
        $owner = strtolower($owner);
        $name = strtolower($name);
        return ['owner' => $owner, 'name' => $name, 'url' => "https://github.com/$owner/$name"];
    }

    private static function jsonColumn(?string $value): ?array
    {
        return $value === null ? null : json_decode($value, true, 32, JSON_THROW_ON_ERROR);
    }

    private static function timestamp(?string $value): ?string
    {
        return $value === null ? null : Carbon::parse($value)->utc()->format('Y-m-d\TH:i:s\Z');
    }

    private static function error(int $status, string $code, string $message, array $details = [], ?int $retryAfter = null): JsonResponse
    {
        $response = response()->json(['schema_version' => 1, 'error' => ['code' => $code, 'message' => $message, 'details' => $details]], $status);
        return $retryAfter === null ? $response : $response->header('Retry-After', (string) $retryAfter);
    }
}
