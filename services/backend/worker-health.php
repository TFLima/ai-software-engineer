<?php
// The worker runs as PID 1. Check process identity and its queue connection.
if (!str_contains(file_get_contents('/proc/1/cmdline'), 'queue:work')) {
    exit(1);
}
require __DIR__.'/vendor/autoload.php';
$app = require __DIR__.'/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
try {
    Illuminate\Support\Facades\Redis::connection()->ping();
} catch (Throwable) {
    exit(1);
}
