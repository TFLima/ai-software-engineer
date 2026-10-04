<?php
namespace App\Providers;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    public function register(): void {}
    public function boot(): void
    {
        \App\Analysis\Policy::validate(config('analysis.limits'));
        config(['queue.connections.redis.retry_after' => config('analysis.limits.redis_reservation_seconds')]);
    }
}
