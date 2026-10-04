<?php

namespace App\Analysis;

use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

final class Lifecycle
{
    public function claim(string $id): ?array
    {
        return DB::transaction(function () use ($id): ?array {
            // Same global lock as admission: serialize the single running slot.
            DB::select('SELECT pg_advisory_xact_lock(20261003, 3)');
            $row = DB::table('analyses')->where('id', $id)->lockForUpdate()->first();
            $now = Carbon::now('UTC');
            $limits = config('analysis.limits');
            if (!$row || $row->status !== 'queued' || $row->active_attempt_id !== null
                || ($row->next_attempt_at && Carbon::parse($row->next_attempt_at)->gt($now))
                || $row->attempt_count >= $limits['total_attempts']
                || DB::table('analyses')->where('status', 'running')->count() >= $limits['active_analyses']) {
                return null;
            }
            $attempt = (string) Str::uuid();
            // Pin the latest known source even if an intervening attempt lost its response.
            $sha = DB::table('analysis_attempts')->where('analysis_id', $id)->whereNotNull('commit_sha')
                ->orderByDesc('attempt_number')->value('commit_sha');
            $deadline = $now->copy()->addSeconds($limits['overall_seconds']);
            DB::table('analysis_attempts')->insert([
                'id' => $attempt, 'analysis_id' => $id, 'attempt_number' => $row->attempt_count + 1,
                'status' => 'running', 'deadline_at' => $deadline,
                'lease_expires_at' => $now->copy()->addSeconds($limits['attempt_lease_seconds']),
                'commit_sha' => $sha, 'selection_policy_version' => '1', 'context_policy_version' => '1',
                'prompt_version' => '1', 'finding_schema_version' => 1,
                'effective_limits' => json_encode($limits, JSON_THROW_ON_ERROR),
                'created_at' => $now, 'updated_at' => $now,
            ]);
            DB::table('analyses')->where('id', $id)->update([
                'status' => 'running', 'active_attempt_id' => $attempt, 'attempt_count' => $row->attempt_count + 1,
                'next_attempt_at' => null, 'started_at' => $now, 'finished_at' => null,
                'commit_sha' => $sha, 'coverage' => null, 'provenance' => null,
                'error_code' => null, 'error_stage' => null, 'updated_at' => $now,
            ]);
            return [
                'schema_version' => 1, 'finding_schema_version' => 1,
                'analysis_id' => $id, 'attempt_id' => $attempt, 'attempt_number' => $row->attempt_count + 1,
                'repository' => ['owner' => $row->repository_owner, 'name' => $row->repository_name, 'url' => $row->repository_url],
                'commit_sha' => $sha, 'deadline_at' => $deadline->format('Y-m-d\TH:i:s\Z'),
                'selection_policy_version' => '1', 'context_policy_version' => '1', 'prompt_version' => '1',
                'limits' => array_intersect_key($limits, array_flip(config('analysis.ai_limit_keys'))),
            ];
        });
    }

    public function fail(array $request, string $code, string $stage, bool $expired = false, ?array $metadata = null): bool
    {
        return DB::transaction(function () use ($request, $code, $stage, $expired, $metadata): bool {
            $row = DB::table('analyses')->where('id', $request['analysis_id'])->lockForUpdate()->first();
            $attempt = DB::table('analysis_attempts')->where('id', $request['attempt_id'])->lockForUpdate()->first();
            if (!$this->matches($row, $attempt, $request)) {
                return false;
            }
            $now = Carbon::now('UTC');
            if (!$expired && Carbon::parse($attempt->deadline_at)->lte($now)) {
                // Late arrivals never mutate anything; reconciliation owns expiry.
                return false;
            }
            if ($expired && Carbon::parse($attempt->lease_expires_at)->gt($now)) {
                return false;
            }
            $limits = json_decode($attempt->effective_limits, true, 32, JSON_THROW_ON_ERROR);
            $retry = in_array($code, Policy::TRANSIENT, true) && $attempt->attempt_number < $limits['automatic_attempts'];
            $values = [];
            if ($metadata !== null) {
                foreach (['commit_sha', 'coverage', 'provenance', 'stage_durations_ms'] as $key) {
                    $values[$key] = is_array($metadata[$key]) ? json_encode($metadata[$key], JSON_THROW_ON_ERROR) : $metadata[$key];
                }
            }
            DB::table('analysis_attempts')->where('id', $attempt->id)->update([
                ...$values, 'status' => $expired ? 'expired' : 'failed', 'error_code' => $code,
                'error_stage' => $stage, 'finished_at' => $now, 'updated_at' => $now,
            ]);
            unset($values['stage_durations_ms']);
            DB::table('analyses')->where('id', $row->id)->update([
                ...$values, 'status' => $retry ? 'queued' : 'failed', 'active_attempt_id' => null,
                'next_attempt_at' => $retry ? $now->copy()->addSeconds($limits['attempt_backoff_seconds']) : null,
                'finished_at' => $retry ? null : $now, 'error_code' => $code, 'error_stage' => $stage, 'updated_at' => $now,
            ]);
            return true;
        });
    }

    public function accept(array $request, array $result): bool
    {
        if ($result['outcome'] === 'failed') {
            return $this->fail($request, $result['error']['code'], $result['error']['stage'], metadata: $result);
        }
        return DB::transaction(function () use ($request, $result): bool {
            $row = DB::table('analyses')->where('id', $request['analysis_id'])->lockForUpdate()->first();
            $attempt = DB::table('analysis_attempts')->where('id', $request['attempt_id'])->lockForUpdate()->first();
            $now = Carbon::now('UTC');
            if (!$this->matches($row, $attempt, $request) || Carbon::parse($attempt->deadline_at)->lte($now)) {
                return false;
            }
            foreach ($result['findings'] as $ordinal => $finding) {
                DB::table('findings')->insert([
                    ...$finding, 'id' => (string) Str::uuid(), 'analysis_id' => $row->id, 'attempt_id' => $attempt->id,
                    'ordinal' => $ordinal, 'evidence' => json_encode($finding['evidence'], JSON_THROW_ON_ERROR),
                    'created_at' => $now, 'updated_at' => $now,
                ]);
            }
            $values = [
                'commit_sha' => $result['commit_sha'], 'coverage' => json_encode($result['coverage'], JSON_THROW_ON_ERROR),
                'provenance' => json_encode($result['provenance'], JSON_THROW_ON_ERROR), 'finished_at' => $now, 'updated_at' => $now,
            ];
            DB::table('analysis_attempts')->where('id', $attempt->id)->update([
                ...$values, 'status' => 'succeeded', 'stage_durations_ms' => json_encode($result['stage_durations_ms'], JSON_THROW_ON_ERROR),
            ]);
            DB::table('analyses')->where('id', $row->id)->update([...$values, 'status' => 'completed', 'active_attempt_id' => null]);
            return true;
        });
    }

    private function matches(?object $row, ?object $attempt, array $request): bool
    {
        return $row && $attempt && $row->status === 'running' && $row->active_attempt_id === $request['attempt_id']
            && $attempt->analysis_id === $row->id && $attempt->status === 'running';
    }

    public function operatorRetry(string $id): bool
    {
        return DB::transaction(function () use ($id): bool {
            DB::select('SELECT pg_advisory_xact_lock(20261003, 3)');
            $row = DB::table('analyses')->where('id', $id)->lockForUpdate()->first();
            $limits = config('analysis.limits');
            if (!$row || $row->status !== 'failed' || !in_array($row->error_code, Policy::TRANSIENT, true)
                || $row->attempt_count >= $limits['total_attempts']
                || DB::table('analyses')->whereIn('status', ['queued', 'running'])->count() >= $limits['queued_analyses']) {
                return false;
            }
            DB::table('analyses')->where('id', $id)->update([
                'status' => 'queued', 'next_attempt_at' => now(), 'finished_at' => null, 'updated_at' => now(),
            ]);
            return true;
        });
    }
}
