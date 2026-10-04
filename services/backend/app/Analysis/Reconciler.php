<?php

namespace App\Analysis;

use Illuminate\Support\Facades\DB;

final class Reconciler
{
    public function run(Lifecycle $lifecycle, Publisher $publisher): void
    {
        DB::table('analysis_attempts')->where('status', 'running')->where('lease_expires_at', '<=', now())
            ->orderBy('id')->chunkById(100, function ($rows) use ($lifecycle, $publisher): void {
                foreach ($rows as $attempt) {
                    if ($lifecycle->fail(['analysis_id' => $attempt->analysis_id, 'attempt_id' => $attempt->id], 'attempt_expired', 'transport', true)
                        && DB::table('analyses')->where('id', $attempt->analysis_id)->where('status', 'queued')->exists()) {
                        $publisher->publish($attempt->analysis_id, config('analysis.limits.attempt_backoff_seconds'));
                    }
                }
            });
        $cutoff = now()->subSeconds(config('analysis.limits.reconcile_seconds'));
        DB::table('analyses')->where('status', 'queued')
            ->where(function ($query) use ($cutoff): void {
                $query->where(function ($q) use ($cutoff): void { $q->whereNull('next_attempt_at')->where('created_at', '<=', $cutoff); })
                    ->orWhere('next_attempt_at', '<=', $cutoff);
            })->orderBy('id')->chunkById(100, function ($rows) use ($publisher): void {
                foreach ($rows as $row) {
                    $publisher->publish($row->id);
                }
            });
    }
}
