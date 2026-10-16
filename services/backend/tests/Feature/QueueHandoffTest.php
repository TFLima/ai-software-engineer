<?php

namespace Tests\Feature;

use App\Analysis\{EnvelopeValidator, InternalClient, Lifecycle, Policy, Publisher};
use App\Jobs\RunAnalysis;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\{DB, Http, Queue};
use Tests\TestCase;

final class QueueHandoffTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        self::assertSame('ai_software_engineer_test', config('database.connections.pgsql.database'));
        Queue::fake();
        Http::preventStrayRequests();
        config(['analysis.internal_secret' => str_repeat('s', 64)]);
    }

    private function submit(string $key = 'one'): string
    {
        return $this->postJson('/api/analyses', ['repository_url' => 'https://github.com/example/small-app'], ['Idempotency-Key' => $key])
            ->assertStatus(202)->json('id');
    }

    private function success(array $request): array
    {
        return [
            'schema_version' => 1, 'finding_schema_version' => 1, 'analysis_id' => $request['analysis_id'],
            'attempt_id' => $request['attempt_id'], 'outcome' => 'succeeded', 'repository' => $request['repository'],
            'commit_sha' => $request['commit_sha'] ?? str_repeat('a', 40),
            'findings' => [[
                'category' => 'reliability', 'severity' => 'medium', 'title' => 'Advisory finding',
                'explanation' => 'A fixture explanation.', 'recommendation' => 'Consider a transaction.',
                'evidence' => [['path' => 'app/a.php', 'start_line' => 10, 'end_line' => 18]],
            ]],
            'coverage' => ['inventory_files' => 1, 'eligible_files' => 1, 'included_files' => 1, 'included_lines' => 9,
                'omitted_files' => 0, 'included_spans' => [['path' => 'app/a.php', 'start_line' => 10, 'end_line' => 18]],
                'omissions' => [], 'limitations' => ['Static inspection only']],
            'provenance' => ['finding_schema_version' => 1, 'selection_policy_version' => '1', 'context_policy_version' => '1',
                'prompt_version' => '1', 'provider' => 'fake', 'model' => 'fixture-v1', 'usage' => ['input_tokens' => 200, 'output_tokens' => 100]],
            'stage_durations_ms' => ['acquire' => 1000, 'select' => 20, 'context' => 30, 'generate' => 500, 'validate' => 20, 'cleanup' => 10],
        ];
    }

    private function validated(array $request, array $result, int $status = 200): ?array
    {
        return app(EnvelopeValidator::class)->validate(json_encode($result, JSON_THROW_ON_ERROR), $status, $request);
    }

    public function test_publish_once_and_single_global_claim(): void
    {
        $id = $this->submit();
        $this->submit();
        Queue::assertPushed(RunAnalysis::class, 1);
        $other = $this->submit('other');
        $lifecycle = app(Lifecycle::class);
        $request = $lifecycle->claim($id);
        self::assertNotNull($request);
        self::assertNull($lifecycle->claim($id));
        self::assertNull($lifecycle->claim($other));
        $attempt = DB::table('analysis_attempts')->first();
        self::assertEquals(config('analysis.limits'), json_decode($attempt->effective_limits, true));
        self::assertEquals(45, \Illuminate\Support\Carbon::parse($attempt->deadline_at)->diffInSeconds($attempt->lease_expires_at));
        $this->assertDatabaseCount('analysis_attempts', 1);
    }

    public function test_automatic_retry_cap_and_one_operator_attempt(): void
    {
        $lifecycle = app(Lifecycle::class);
        $id = $this->submit();
        $first = $lifecycle->claim($id);
        self::assertTrue($lifecycle->fail($first, 'network_unavailable', 'transport'));
        self::assertNull($lifecycle->claim($id));
        $this->travel(5)->seconds();
        $second = $lifecycle->claim($id);
        self::assertNotSame($first['attempt_id'], $second['attempt_id']);
        $lifecycle->fail($second, 'upstream_timeout', 'transport');
        self::assertNull($lifecycle->claim($id));
        $this->artisan('analyses:retry', ['id' => $id])->assertSuccessful();
        $third = $lifecycle->claim($id);
        self::assertSame(3, $third['attempt_number']);
        $lifecycle->fail($third, 'upstream_unavailable', 'transport');
        self::assertFalse($lifecycle->operatorRetry($id));
        $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'failed', 'attempt_count' => 3]);
    }

    public function test_terminal_failure_cannot_retry(): void
    {
        $id = $this->submit();
        $lifecycle = app(Lifecycle::class);
        $lifecycle->fail($lifecycle->claim($id), 'invalid_result', 'transport');
        self::assertNull($lifecycle->claim($id));
        self::assertFalse($lifecycle->operatorRetry($id));
        $this->artisan('analyses:retry', ['id' => $id])->assertFailed();
    }

    public function test_reconciliation_recovers_queue_loss_and_waits_for_lease(): void
    {
        $id = $this->submit();
        Queue::fake();
        $this->travel(29)->seconds();
        $this->artisan('analyses:reconcile')->assertSuccessful();
        Queue::assertNothingPushed();
        $this->travel(1)->seconds();
        $this->artisan('analyses:reconcile')->assertSuccessful();
        Queue::assertPushed(RunAnalysis::class, 1);
        $lifecycle = app(Lifecycle::class);
        $request = $lifecycle->claim($id);
        $this->travel(241)->seconds();
        self::assertFalse($lifecycle->accept($request, $this->validated($request, $this->success($request))));
        $this->artisan('analyses:reconcile')->assertSuccessful();
        $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'running']);
        $this->travel(44)->seconds();
        $this->artisan('analyses:reconcile')->assertSuccessful();
        $this->assertDatabaseHas('analysis_attempts', ['id' => $request['attempt_id'], 'status' => 'expired']);
        $this->travel(5)->seconds();
        $next = $lifecycle->claim($id);
        self::assertNotSame($request['attempt_id'], $next['attempt_id']);
        self::assertFalse($lifecycle->fail($request, 'configuration_error', 'request'));
        self::assertFalse($lifecycle->accept($request, $this->validated($request, $this->success($request))));
        $this->assertDatabaseHas('analyses', ['id' => $id, 'active_attempt_id' => $next['attempt_id']]);
    }

    public function test_completed_results_are_immutable_and_mismatched_results_ignored(): void
    {
        $id = $this->submit();
        $lifecycle = app(Lifecycle::class);
        $request = $lifecycle->claim($id);
        $result = $this->success($request);
        $wrong = $result;
        $wrong['attempt_id'] = '33333333-3333-4333-8333-333333333333';
        self::assertNull($this->validated($request, $wrong));
        self::assertTrue($lifecycle->accept($request, $this->validated($request, $result)));
        self::assertFalse($lifecycle->accept($request, $this->validated($request, $result)));
        self::assertFalse($lifecycle->fail($request, 'configuration_error', 'request'));
        self::assertFalse($lifecycle->operatorRetry($id));
        $this->assertDatabaseCount('findings', 1);
        $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'completed', 'active_attempt_id' => null]);
        $this->getJson("/api/analyses/$id/findings")->assertOk()->assertJsonCount(1, 'data');
    }

    public function test_transport_never_resends_and_auth_failure_is_terminal(): void
    {
        $id = $this->submit();
        Http::fake(['*' => Http::failedConnection()]);
        (new RunAnalysis($id))->handle(app(Lifecycle::class), app(InternalClient::class), app(Publisher::class));
        Http::assertSentCount(1);
        $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'queued', 'error_code' => 'network_unavailable']);
        $this->travel(5)->seconds();
        Http::swap(new \Illuminate\Http\Client\Factory);
        Http::fake(['*' => Http::response(['schema_version' => 1, 'error' => ['code' => 'unauthorized_internal', 'stage' => 'request', 'retryable' => false]], 401)]);
        (new RunAnalysis($id))->handle(app(Lifecycle::class), app(InternalClient::class), app(Publisher::class));
        Http::assertSent(fn ($r) => $r->hasHeader('Authorization', 'Bearer '.str_repeat('s', 64)) && $r['attempt_number'] === 2);
        $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'failed', 'error_code' => 'unauthorized_internal']);
    }

    public function test_missing_secret_and_non_json_are_terminal(): void
    {
        $id = $this->submit();
        config(['analysis.internal_secret' => '']);
        (new RunAnalysis($id))->handle(app(Lifecycle::class), app(InternalClient::class), app(Publisher::class));
        Http::assertNothingSent();
        $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'failed', 'error_code' => 'configuration_error']);
        config(['analysis.internal_secret' => str_repeat('s', 64)]);
        $id = $this->submit('other');
        Http::fake(['*' => Http::response('<html>secret</html>', 502, ['Content-Type' => 'text/html'])]);
        (new RunAnalysis($id))->handle(app(Lifecycle::class), app(InternalClient::class), app(Publisher::class));
        $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'failed', 'error_code' => 'invalid_result']);
    }

    public function test_failure_preserves_provenance_and_pins_retry(): void
    {
        $lifecycle = app(Lifecycle::class);
        $id = $this->submit();
        $request = $lifecycle->claim($id);
        $result = $this->success($request);
        unset($result['findings']);
        $result['outcome'] = 'failed';
        $result['error'] = ['code' => 'upstream_unavailable', 'stage' => 'generate', 'retryable' => true];
        $lifecycle->accept($request, $this->validated($request, $result, 502));
        $this->travel(5)->seconds();
        $next = $lifecycle->claim($id);
        self::assertSame(str_repeat('a', 40), $next['commit_sha']);
        $bad = $this->success($next);
        $bad['commit_sha'] = str_repeat('b', 40);
        $this->expectException(\DomainException::class);
        $this->validated($next, $bad);
    }

    public function test_strict_response_boundaries_reject_entire_candidate(): void
    {
        $request = app(Lifecycle::class)->claim($this->submit());
        $valid = $this->success($request);
        $mutations = [
            function (&$r) { $r['extra'] = 'bad'; },
            function (&$r) { $r['schema_version'] = 2; },
            function (&$r) { $r['coverage']['included_lines'] = 1; },
            function (&$r) { $r['findings'][0]['evidence'][0]['end_line'] = 19; },
            function (&$r) { $r['findings'][0]['evidence'][0]['path'] = '../secret'; },
            function (&$r) { $r['findings'][0]['evidence'][0]['start_line'] = true; },
            function (&$r) { $r['findings'][0]['confidence'] = null; },
            function (&$r) { $r['findings'][0]['extra'] = 'bad'; },
            function (&$r) { $r['provenance']['prompt_version'] = '2'; },
            function (&$r) { $r['provenance']['usage']['input_tokens'] = -1; },
            function (&$r) { $r['findings'] = array_fill(0, 21, $r['findings'][0]); },
            function (&$r) { $r['stage_durations_ms']['acquire'] = 75001; },
            function (&$r) { $r['findings'] = new \stdClass; },
        ];
        foreach ($mutations as $mutate) {
            $result = $valid;
            $mutate($result);
            try {
                $this->validated($request, $result);
                self::fail('Accepted invalid response');
            } catch (\DomainException) {
                self::assertTrue(true);
            }
        }
        $valid['findings'] = [];
        self::assertNotNull($this->validated($request, $valid));
        $this->assertDatabaseCount('findings', 0);
    }

    public function test_failed_publication_remains_durable_and_is_reconciled(): void
    {
        Queue::swap(\Mockery::mock(\Illuminate\Queue\QueueManager::class));
        Queue::shouldReceive('connection')->once()->with('redis')->andThrow(new \RuntimeException('private transport data'));
        $id = $this->submit();
        $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'queued', 'attempt_count' => 0]);
        Queue::swap($this->app->make('queue'));
        Queue::fake();
        $this->travel(31)->seconds();
        $this->artisan('analyses:reconcile')->assertSuccessful();
        Queue::assertPushed(RunAnalysis::class);
    }

    public function test_oversize_and_duplicate_key_responses_are_terminal(): void
    {
        foreach ([str_repeat('x', 1048577), '{"schema_version":1,"schema_version":1}'] as $index => $body) {
            Http::swap(new \Illuminate\Http\Client\Factory);
            Http::fake(['*' => Http::response($body, 200, ['Content-Type' => 'application/json'])]);
            $id = $this->submit('bad-'.$index);
            (new RunAnalysis($id))->handle(app(Lifecycle::class), app(InternalClient::class), app(Publisher::class));
            $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'failed', 'error_code' => 'invalid_result']);
        }
        $this->assertDatabaseCount('findings', 0);
    }

    public function test_failure_retryability_and_http_mapping_must_agree(): void
    {
        $request = app(Lifecycle::class)->claim($this->submit());
        $result = $this->success($request);
        unset($result['findings']);
        $result['outcome'] = 'failed';
        $result['error'] = ['code' => 'invalid_findings', 'stage' => 'validate', 'retryable' => true];
        try {
            $this->validated($request, $result, 422);
            self::fail('Accepted contradictory retryability');
        } catch (\DomainException) {
            self::assertTrue(true);
        }
        $result['error']['retryable'] = false;
        $this->expectException(\DomainException::class);
        $this->validated($request, $result, 200);
    }

    public function test_atomic_findings_rollback_on_database_failure(): void
    {
        $id = $this->submit();
        $lifecycle = app(Lifecycle::class);
        $request = $lifecycle->claim($id);
        $result = $this->success($request);
        $result['findings'][] = $result['findings'][0];
        $result = $this->validated($request, $result);
        DB::unprepared("CREATE FUNCTION test_reject_second() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.ordinal = 1 THEN RAISE EXCEPTION 'fixture'; END IF; RETURN NEW; END $$");
        DB::unprepared('CREATE TRIGGER reject_second BEFORE INSERT ON findings FOR EACH ROW EXECUTE FUNCTION test_reject_second()');
        try {
            $lifecycle->accept($request, $result);
            self::fail('Database fixture did not reject second finding');
        } catch (\Illuminate\Database\QueryException) {
            $this->assertDatabaseCount('findings', 0);
            $this->assertDatabaseHas('analyses', ['id' => $id, 'status' => 'running']);
            $this->assertDatabaseHas('analysis_attempts', ['id' => $request['attempt_id'], 'status' => 'running']);
        }
    }

    public function test_python_orchestrator_fixture_is_revalidated_and_persisted_once(): void
    {
        $id = $this->submit();
        $lifecycle = app(Lifecycle::class);
        $request = $lifecycle->claim($id);
        $result = json_decode(file_get_contents(__DIR__.'/../Fixtures/b10-success.json'), true, 32, JSON_THROW_ON_ERROR);
        $result['analysis_id'] = $request['analysis_id'];
        $result['attempt_id'] = $request['attempt_id'];
        $validated = $this->validated($request, $result);
        self::assertTrue($lifecycle->accept($request, $validated));
        self::assertFalse($lifecycle->accept($request, $validated));
        $this->assertDatabaseCount('findings', 1);
        $this->assertDatabaseHas('analysis_attempts', ['id' => $request['attempt_id'], 'status' => 'succeeded']);
        $this->getJson("/api/analyses/$id")->assertOk()->assertJsonPath('status', 'completed');
        $this->getJson("/api/analyses/$id/findings")->assertOk()->assertJsonCount(1, 'data');
    }

    public function test_timeout_ordering_is_checked(): void
    {
        $limits = config('analysis.limits');
        $limits['worker_http_seconds'] = $limits['overall_seconds'];
        $this->expectException(\LogicException::class);
        Policy::validate($limits);
    }
}
