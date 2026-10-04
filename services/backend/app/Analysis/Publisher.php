<?php

namespace App\Analysis;

use App\Jobs\RunAnalysis;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Queue;

final class Publisher
{
    public function publish(string $id, int $delay = 0): bool
    {
        try {
            Queue::connection('redis')->later($delay, new RunAnalysis($id));
            return true;
        } catch (\Throwable) {
            // The durable queued row remains the publication intent. Never log exception bodies.
            Log::warning('analysis_queue_publication_failed', ['analysis_id' => $id, 'code' => 'queue_unavailable']);
            return false;
        }
    }
}
