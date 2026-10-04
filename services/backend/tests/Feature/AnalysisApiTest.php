<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class AnalysisApiTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        \Illuminate\Support\Facades\Queue::fake();
        // RefreshDatabase must never reset the operator's retained analyses.
        self::assertSame('ai_software_engineer_test', config('database.connections.pgsql.database'));
    }

    private function submit(string $json, string $key = 'demo-key')
    {
        return $this->call('POST', '/api/analyses', [], [], [], [
            'CONTENT_TYPE' => 'application/json',
            'HTTP_ACCEPT' => 'application/json',
            'HTTP_IDEMPOTENCY_KEY' => $key,
        ], $json);
    }

    public function test_submission_canonical_replay_conflict_and_new_key(): void
    {
        $first = $this->submit('{"repository_url":"https://github.com/Example/Small-App.git/"}')
            ->assertStatus(202)->assertJsonPath('status', 'queued');
        $id = $first->json('id');
        $first->assertHeader('Location', "/api/analyses/$id");
        $this->assertDatabaseHas('analyses', [
            'id' => $id,
            'repository_url' => 'https://github.com/example/small-app',
            'request_hash' => hash('sha256', '{"repository_url":"https://github.com/example/small-app"}'),
            'attempt_count' => 0,
        ]);
        $this->submit('{"repository_url":"https://GITHUB.COM/example/small-app"}')
            ->assertStatus(202)->assertJsonPath('id', $id);
        DB::table('analyses')->where('id', $id)->update(['status' => 'failed']);
        $this->submit('{"repository_url":"https://github.com/example/small-app"}')
            ->assertStatus(202)->assertJsonPath('status', 'failed');
        $this->submit('{"repository_url":"https://github.com/example/another"}')
            ->assertStatus(409)->assertJsonPath('error.code', 'idempotency_conflict');
        $this->submit('{"repository_url":"https://github.com/example/small-app"}', 'second-key')
            ->assertStatus(202);
        $this->assertDatabaseCount('analyses', 2);
    }

    public function test_validation_rejects_unsafe_urls_unknown_fields_and_duplicate_keys_without_binding(): void
    {
        foreach ([
            'http://github.com/a/b', 'https://github.com/a/b?x=1',
            'https://github.com/a/b/c', 'https://github.com/a:443/b',
            'https://github.com/a--b/repo', 'https://github.com/a/%62',
            'https://github.com/a/.git',
        ] as $url) {
            $this->submit(json_encode(['repository_url' => $url]))
                ->assertStatus(422)->assertJsonPath('error.details.0.code', 'invalid_repository_url');
        }
        $this->submit('{"repository_url":"https://github.com/a/b","branch":"main"}')
            ->assertStatus(422)->assertJsonPath('error.details.0.field', 'branch');
        $this->submit('{"repository_url":"https://github.com/a/b","repository_url":"https://github.com/a/c"}')
            ->assertStatus(400)->assertJsonPath('error.code', 'invalid_json');
        $this->submit('{"repository_url":"https://github.com/a/b","\\u0072epository_url":"https://github.com/a/c"}')
            ->assertStatus(400)->assertJsonPath('error.code', 'invalid_json');
        $this->submit('{"repository_url":"https://github.com/a/b",}')
            ->assertStatus(400);
        $this->submit('[]')->assertStatus(422)->assertJsonPath('error.details.0.code', 'invalid_type');
        $this->submit('{"repository_url":"https://github.com/a/b"}', 'bad key')
            ->assertStatus(422)->assertJsonPath('error.details.0.code', 'invalid_idempotency_key');
        $this->assertDatabaseCount('analyses', 0);
    }

    public function test_submission_limits_allow_replay_before_rate_limit(): void
    {
        for ($i = 0; $i < 6; $i++) {
            $this->submit('{"repository_url":"https://github.com/a/b"}', "key-$i")->assertStatus(202);
        }
        $this->submit('{"repository_url":"https://github.com/a/b"}', 'key-0')->assertStatus(202);
        $this->submit('{"repository_url":"https://github.com/a/b"}', 'key-6')
            ->assertStatus(429)->assertHeader('Retry-After', '60');
        $this->assertDatabaseCount('analyses', 6);
    }

    public function test_queued_slot_limit_is_enforced_after_rate_window(): void
    {
        for ($i = 0; $i < 10; $i++) {
            DB::table('analyses')->insert([
                'id' => sprintf('11111111-1111-4111-8111-%012d', $i),
                'idempotency_key' => "old-$i", 'request_hash' => str_repeat('a', 64),
                'repository_owner' => 'a', 'repository_name' => 'b',
                'repository_url' => 'https://github.com/a/b', 'status' => 'queued',
                'attempt_count' => 0, 'created_at' => now()->subMinutes(2),
                'updated_at' => now()->subMinutes(2),
            ]);
        }
        $this->submit('{"repository_url":"https://github.com/a/b"}', 'new-key')
            ->assertStatus(429)->assertHeader('Retry-After', '60');
        $this->assertDatabaseCount('analyses', 10);
    }

    public function test_status_and_findings_readiness_and_pagination(): void
    {
        $id = $this->submit('{"repository_url":"https://github.com/a/b"}')->json('id');
        $this->getJson("/api/analyses/$id")->assertOk()
            ->assertJsonPath('attempt_count', 0)
            ->assertJsonPath('repository.url', 'https://github.com/a/b')
            ->assertJsonPath('coverage', null);
        $this->getJson("/api/analyses/$id/findings")
            ->assertStatus(409)->assertJsonPath('error.code', 'analysis_not_completed');
        $this->getJson("/api/analyses/$id/findings?page=0")
            ->assertStatus(422)->assertJsonPath('error.details.0.code', 'out_of_range');
        $this->getJson("/api/analyses/$id/findings?filter=security")
            ->assertStatus(422)->assertJsonPath('error.details.0.code', 'unknown_field');

        DB::table('analyses')->where('id', $id)->update([
            'status' => 'running', 'active_attempt_id' => '22222222-2222-4222-8222-222222222222',
        ]);
        $this->getJson("/api/analyses/$id/findings")->assertStatus(409);
        DB::table('analyses')->where('id', $id)->update(['status' => 'failed', 'active_attempt_id' => null]);
        $this->getJson("/api/analyses/$id/findings")->assertStatus(409);

        $attempt = '22222222-2222-4222-8222-222222222222';
        $sha = str_repeat('a', 40);
        DB::table('analysis_attempts')->insert([
            'id' => $attempt, 'analysis_id' => $id, 'attempt_number' => 1,
            'status' => 'succeeded', 'deadline_at' => now()->addMinutes(4),
            'lease_expires_at' => now()->addMinutes(5), 'commit_sha' => $sha,
            'selection_policy_version' => '1', 'context_policy_version' => '1',
            'prompt_version' => '1', 'finding_schema_version' => 1,
            'effective_limits' => '{}', 'created_at' => now(), 'updated_at' => now(),
        ]);
        DB::table('analyses')->where('id', $id)->update([
            'status' => 'completed', 'attempt_count' => 1, 'commit_sha' => $sha,
            'coverage' => json_encode(['inventory_files' => 1, 'included_spans' => [['path' => 'a.php', 'start_line' => 1, 'end_line' => 1]]]),
        ]);
        for ($i = 0; $i < 3; $i++) {
            DB::table('findings')->insert([
                'id' => sprintf('33333333-3333-4333-8333-%012d', $i),
                'analysis_id' => $id, 'attempt_id' => $attempt, 'ordinal' => $i,
                'category' => 'testing', 'severity' => 'low', 'title' => "Finding $i",
                'explanation' => 'Explanation', 'recommendation' => 'Recommendation',
                'confidence' => $i === 1 ? 0.712345 : null,
                'evidence' => json_encode([['path' => 'a.php', 'start_line' => 1, 'end_line' => 1]]),
                'created_at' => now(), 'updated_at' => now(),
            ]);
        }
        $this->getJson("/api/analyses/$id")->assertOk()
            ->assertJsonMissingPath('coverage.included_spans');
        $this->getJson("/api/analyses/$id/findings?page=2&per_page=2")->assertOk()
            ->assertJsonCount(1, 'data')->assertJsonPath('data.0.title', 'Finding 2')
            ->assertJsonPath('pagination.total_pages', 2);
        $this->getJson("/api/analyses/$id/findings?per_page=2")->assertOk()
            ->assertJsonMissingPath('data.0.confidence')
            ->assertJsonPath('data.1.confidence', 0.712345);
        $this->getJson("/api/analyses/$id/findings?page=3&per_page=2")->assertOk()
            ->assertJsonCount(0, 'data')->assertJsonPath('pagination.total', 3);
        DB::table('findings')->where('analysis_id', $id)->delete();
        $this->getJson("/api/analyses/$id/findings")->assertOk()
            ->assertJsonCount(0, 'data')->assertJsonPath('pagination.total_pages', 0);
        $this->getJson('/api/analyses/not-a-uuid')->assertStatus(404);
        $this->getJson('/api/analyses/not-a-uuid/extra')
            ->assertStatus(404)->assertJsonPath('error.code', 'analysis_not_found');
        $this->getJson('/api/analyses/11111111-1111-4111-8111-111111111111/findings')->assertStatus(404);
    }
}
