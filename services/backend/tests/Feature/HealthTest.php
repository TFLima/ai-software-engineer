<?php
namespace Tests\Feature;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Redis;
use Tests\TestCase;

class HealthTest extends TestCase
{
    public function test_ready_when_database_and_redis_respond(): void
    {
        DB::shouldReceive('select')->once()->with('SELECT 1')->andReturn([(object) ['value' => 1]]);
        Redis::shouldReceive('connection->ping')->once()->andReturn(true);
        $this->getJson('/api/health')->assertOk()->assertExactJson([
            'status' => 'ok', 'service' => 'application',
        ]);
    }
    public function test_dependency_failure_is_unavailable_without_details(): void
    {
        DB::shouldReceive('select')->once()->andThrow(new \RuntimeException('sensitive connection detail'));
        $this->getJson('/api/health')->assertStatus(503)->assertExactJson([
            'status' => 'unavailable', 'service' => 'application',
        ]);
    }
    public function test_redis_failure_is_unavailable_without_details(): void
    {
        DB::shouldReceive('select')->once()->with('SELECT 1')->andReturn([]);
        Redis::shouldReceive('connection->ping')->once()->andThrow(new \RuntimeException('sensitive redis detail'));
        $this->getJson('/api/health')->assertStatus(503)->assertExactJson([
            'status' => 'unavailable', 'service' => 'application',
        ]);
    }
}
