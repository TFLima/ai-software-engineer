<?php

namespace Tests\Feature;

use App\Analysis\{Lifecycle, Retention};
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\{DB, Queue};
use Tests\TestCase;

final class OperationsTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        self::assertSame('ai_software_engineer_test', config('database.connections.pgsql.database'));
        Queue::fake();
    }

    private function submit(string $key): string
    {
        return $this->postJson('/api/analyses', ['repository_url' => 'https://github.com/example/small-app'],
            ['Idempotency-Key' => $key])->assertStatus(202)->json('id');
    }

    public function test_retention_cascades_results_and_preserves_pending_work(): void
    {
        $old = $this->submit('old');
        $request = app(Lifecycle::class)->claim($old);
        $result = json_decode(file_get_contents(__DIR__.'/../Fixtures/b10-success.json'), true, 32, JSON_THROW_ON_ERROR);
        self::assertTrue(app(Lifecycle::class)->accept($request, $result));
        self::assertGreaterThan(0, DB::table('findings')->where('analysis_id', $old)->count());
        DB::table('analyses')->where('id', $old)->update(['finished_at' => now()->subDays(31)]);
        $queued = $this->submit('queued');
        $running = $this->submit('running');
        app(Lifecycle::class)->claim($running);
        self::assertSame(1, app(Retention::class)->purge());
        self::assertFalse(DB::table('analyses')->where('id', $old)->exists());
        self::assertSame(0, DB::table('analysis_attempts')->where('analysis_id', $old)->count());
        self::assertSame(0, DB::table('findings')->where('analysis_id', $old)->count());
        self::assertTrue(DB::table('analyses')->where('id', $queued)->exists());
        self::assertSame(0, app(Retention::class)->purge($running));
        // Deletion also expires submission idempotency; resubmission creates a new row.
        self::assertNotSame($old, $this->submit('old'));
    }

    public function test_recent_terminal_result_requires_explicit_deletion(): void
    {
        $id = $this->submit('recent');
        $request = app(Lifecycle::class)->claim($id);
        app(Lifecycle::class)->fail($request, 'invalid_findings', 'validate');
        self::assertSame(0, app(Retention::class)->purge());
        $this->artisan('analyses:inspect', ['id' => $id])->expectsOutputToContain('invalid_findings')->assertSuccessful();
        $this->artisan('analyses:purge', ['--id' => $id])->assertSuccessful();
        $this->getJson('/api/analyses/'.$id)->assertNotFound();
        $this->artisan('analyses:purge', ['--id' => $id])->assertFailed();
    }

    public function test_operator_commands_reject_invalid_ids(): void
    {
        $this->artisan('analyses:inspect', ['id' => 'invalid'])->assertFailed();
        $this->artisan('analyses:purge', ['--id' => 'invalid'])->assertFailed();
    }
}
