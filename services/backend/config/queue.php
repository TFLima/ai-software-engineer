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
    // B03 records durable queued analyses; B04 implements queue publication.
    'failed' => ['driver' => 'null'],
];
