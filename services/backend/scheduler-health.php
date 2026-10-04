<?php
if (!str_contains(file_get_contents('/proc/1/cmdline'), 'schedule:work')) {
    exit(1);
}
require __DIR__.'/vendor/autoload.php';
$app = require __DIR__.'/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
try {
    Illuminate\Support\Facades\DB::select('SELECT 1');
    Illuminate\Support\Facades\Redis::connection()->ping();
} catch (Throwable) {
    exit(1);
}
