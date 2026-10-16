<?php

namespace App\Console\Commands;

use App\Analysis\Retention;
use Illuminate\Console\Command;

final class PurgeAnalyses extends Command
{
    protected $signature = 'analyses:purge {--id= : Delete one terminal analysis immediately}';
    protected $description = 'Delete expired terminal results, attempts and idempotency records';

    public function handle(Retention $retention): int
    {
        $id = $this->option('id');
        if ($id !== null && (!is_string($id) || !preg_match('/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/D', $id))) {
            $this->error('Invalid analysis ID.');
            return self::FAILURE;
        }
        $count = $retention->purge($id);
        $this->info("Deleted terminal analyses: {$count}");
        return $id !== null && $count === 0 ? self::FAILURE : self::SUCCESS;
    }
}
