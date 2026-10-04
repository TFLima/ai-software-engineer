<?php
return [
    'default' => 'redis',
    'connections' => [
        'redis' => [
            'driver' => 'redis', 'connection' => 'default', 'queue' => 'default',
            // B01 reservation exceeds the 270-second job timeout.
            'retry_after' => 300, 'block_for' => 5, 'after_commit' => false,
        ],
    ],
    // Domain attempt history is durable; framework retries must not allocate attempts.
    'failed' => ['driver' => 'null'],
];
