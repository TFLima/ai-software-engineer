<?php

namespace App\Analysis;

use Illuminate\Support\Facades\DB;

final class Retention
{
    public function purge(?string $id = null): int
    {
        $deleted = 0;
        $query = DB::table('analyses')->whereIn('status', ['completed', 'failed']);
        if ($id !== null) {
            $query->where('id', $id);
        } else {
            $query->where('finished_at', '<=', now()->subDays(config('analysis.retention_days')));
        }
        $query->orderBy('id')->chunkById(100, function ($rows) use (&$deleted, $id): void {
            foreach ($rows as $candidate) {
                $deleted += DB::transaction(function () use ($candidate, $id): int {
                    // Serialize with retry/accept so active work is never deleted.
                    $row = DB::table('analyses')->where('id', $candidate->id)->lockForUpdate()->first();
                    if (!$row || !in_array($row->status, ['completed', 'failed'], true)
                        || $row->active_attempt_id !== null
                        || ($id === null && (!$row->finished_at
                            || \Illuminate\Support\Carbon::parse($row->finished_at)->gt(now()->subDays(config('analysis.retention_days')))))) {
                        return 0;
                    }
                    // Foreign keys cascade attempts and findings in this transaction.
                    return DB::table('analyses')->where('id', $row->id)->delete();
                });
            }
        });
        return $deleted;
    }
}
