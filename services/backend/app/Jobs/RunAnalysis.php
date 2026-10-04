<?php

namespace App\Jobs;

use App\Analysis\InternalClient;
use App\Analysis\Lifecycle;
use App\Analysis\Publisher;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;

final class RunAnalysis implements ShouldQueue
{
    use Queueable;

    public int $tries = 1;
    public int $timeout;
    public bool $failOnTimeout = true;

    public function __construct(public readonly string $analysisId)
    {
        $this->timeout = config('analysis.limits.job_seconds');
    }

    public function handle(Lifecycle $lifecycle, InternalClient $client, Publisher $publisher): void
    {
        $request = $lifecycle->claim($this->analysisId);
        if ($request === null) {
            return;
        }
        $client->run($request, $lifecycle);
        // Safe duplicate publication after a retry. Final state/eligibility is checked at claim.
        if (\Illuminate\Support\Facades\DB::table('analyses')->where('id', $this->analysisId)->where('status', 'queued')->exists()) {
            $publisher->publish($this->analysisId, config('analysis.limits.attempt_backoff_seconds'));
        }
    }
    // Worker crashes are intentionally recovered by lease reconciliation, not framework retries.
}
