<?php

namespace Tests\Feature;

use App\Analysis\{Lifecycle, Retention};
use Illuminate\Console\Scheduling\Schedule;
use Illuminate\Foundation\Testing\DatabaseMigrations;
use Illuminate\Support\Facades\{DB, Queue};
use Tests\TestCase;

final class RetentionScheduleTest extends TestCase
{
    use DatabaseMigrations;

    protected function setUp(): void
    {
        parent::setUp();
        self::assertSame('ai_software_engineer_test', config('database.connections.pgsql.database'));
        Queue::fake();
    }

    private function expiredFailure(string $key): string
    {
        $id = $this->postJson('/api/analyses', ['repository_url' => 'https://github.com/example/small-app'],
            ['Idempotency-Key' => $key])->assertStatus(202)->json('id');
        $first = app(Lifecycle::class)->claim($id);
        self::assertTrue(app(Lifecycle::class)->fail($first, 'upstream_unavailable', 'generate'));
        DB::table('analyses')->where('id', $id)->update(['next_attempt_at' => now()->subSecond()]);
        $second = app(Lifecycle::class)->claim($id);
        self::assertTrue(app(Lifecycle::class)->fail($second, 'upstream_unavailable', 'generate'));
        DB::table('analyses')->where('id', $id)->update(['finished_at' => now()->subDays(31)]);
        return $id;
    }

    public function test_purge_rechecks_row_after_concurrent_operator_retry(): void
    {
        $id = $this->expiredFailure('race');
        $process = null;
        $pipes = [];
        $eligible = null;
        $blocked = false;

        DB::transaction(function () use ($id, &$process, &$pipes, &$eligible, &$blocked): void {
            $row = DB::table('analyses')->where('id', $id)->lockForUpdate()->first();
            self::assertSame('failed', $row->status);
            $script = <<<'PHP'
require 'vendor/autoload.php';
$app = require 'bootstrap/app.php';
$app->make(\Illuminate\Contracts\Console\Kernel::class)->bootstrap();
echo 'pid='.\Illuminate\Support\Facades\DB::selectOne('SELECT pg_backend_pid() AS pid')->pid.' eligible='.\Illuminate\Support\Facades\DB::table('analyses')->where('status', 'failed')->where('finished_at', '<=', now()->subDays(config('analysis.retention_days')))->count()."\n";
flush();
echo 'deleted='.app(\App\Analysis\Retention::class)->purge()."\n";
PHP;
            $process = proc_open(['php', '-r', $script],
                [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes, base_path());
            self::assertNotFalse($process);
            stream_set_timeout($pipes[1], 10);
            $eligible = trim((string) fgets($pipes[1]));
            self::assertMatchesRegularExpression('/^pid=[0-9]+ eligible=1$/', $eligible);
            $backend = (int) explode(' ', substr($eligible, 4))[0];
            for ($attempt = 0; $attempt < 100; $attempt++) {
                $wait = DB::selectOne('SELECT wait_event_type FROM pg_stat_activity WHERE pid = ?', [$backend]);
                if ($wait && $wait->wait_event_type === 'Lock') {
                    $blocked = true;
                    break;
                }
                usleep(50000);
            }
            self::assertTrue(app(Lifecycle::class)->operatorRetry($id));
        });

        $output = stream_get_contents($pipes[1]);
        $error = stream_get_contents($pipes[2]);
        fclose($pipes[1]);
        fclose($pipes[2]);
        self::assertSame(0, proc_close($process), $error);
        self::assertTrue($blocked, 'Purge never waited for the row lock');
        self::assertStringContainsString('deleted=0', $output);
        self::assertSame('queued', DB::table('analyses')->where('id', $id)->value('status'));
        self::assertSame(2, DB::table('analysis_attempts')->where('analysis_id', $id)->count());
    }

    public function test_hourly_schedule_purges_expired_terminal_analysis(): void
    {
        $id = $this->expiredFailure('scheduled');
        $this->travelTo(now()->startOfHour());
        $due = app(Schedule::class)->dueEvents(app());
        $purge = collect($due)->first(fn ($event) => str_contains($event->command, 'analyses:purge'));
        self::assertNotNull($purge, 'Hourly purge is not due');
        $purge->run(app());
        self::assertFalse(DB::table('analyses')->where('id', $id)->exists());
    }

    public function test_retry_cannot_reopen_an_already_purged_failure(): void
    {
        $id = $this->expiredFailure('purge-first');
        self::assertSame(1, app(Retention::class)->purge());
        self::assertFalse(app(Lifecycle::class)->operatorRetry($id));
        self::assertSame(0, DB::table('analysis_attempts')->where('analysis_id', $id)->count());
    }
}
