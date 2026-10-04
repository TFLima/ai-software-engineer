<?php

namespace App\Console\Commands;

use App\Analysis\Lifecycle;
use App\Analysis\Publisher;
use Illuminate\Console\Command;

final class RetryAnalysis extends Command
{
    protected $signature = 'analyses:retry {id}';
    protected $description = 'Explicit operator retry of a transient terminal failure';

    public function handle(Lifecycle $lifecycle, Publisher $publisher): int
    {
        $id = $this->argument('id');
        if (!is_string($id) || !preg_match('/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/D', $id)
            || !$lifecycle->operatorRetry($id)) {
            $this->error('Analysis is not eligible for operator retry.');
            return self::FAILURE;
        }
        $publisher->publish($id);
        $this->info('Analysis queued; reconciliation will recover any publication failure.');
        return self::SUCCESS;
    }
}
