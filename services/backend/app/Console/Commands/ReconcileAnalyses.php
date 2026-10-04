<?php

namespace App\Console\Commands;

use App\Analysis\Lifecycle;
use App\Analysis\Publisher;
use App\Analysis\Reconciler;
use Illuminate\Console\Command;

final class ReconcileAnalyses extends Command
{
    protected $signature = 'analyses:reconcile';
    protected $description = 'Recover lost queue delivery and expired attempt leases';

    public function handle(Reconciler $reconciler, Lifecycle $lifecycle, Publisher $publisher): int
    {
        $reconciler->run($lifecycle, $publisher);
        return self::SUCCESS;
    }
}
