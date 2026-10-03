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
    // No queue tables/domain persistence in B02.
    'failed' => ['driver' => 'null'],
];
