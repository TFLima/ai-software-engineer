<?php
namespace App\Providers;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    public function register(): void {}
    public function boot(): void
    {
        $days = config('analysis.retention_days');
        if (filter_var($days, FILTER_VALIDATE_INT) === false || (int) $days < 1 || (int) $days > 3650) {
            throw new \RuntimeException('Invalid analysis retention configuration.');
        }
        \App\Analysis\Policy::validate(config('analysis.limits'));
        config(['queue.connections.redis.retry_after' => config('analysis.limits.redis_reservation_seconds')]);
    }
}
