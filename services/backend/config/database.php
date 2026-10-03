<?php
return [
    'default' => 'pgsql',
    'connections' => [
        'pgsql' => [
            'driver' => 'pgsql',
            'host' => env('DB_HOST', 'postgres'),
            'port' => env('DB_PORT', '5432'),
            'database' => env('DB_DATABASE', 'ai_software_engineer'),
            'username' => env('DB_USERNAME', 'ai_software_engineer'),
            'password' => env('DB_PASSWORD'),
            'charset' => 'utf8', 'prefix' => '', 'search_path' => 'public', 'sslmode' => 'prefer',
        ],
    ],
    'redis' => [
        'client' => 'predis',
        'options' => ['prefix' => 'ai_software_engineer:'],
        'default' => [
            'host' => env('REDIS_HOST', 'redis'),
            'port' => env('REDIS_PORT', '6379'),
            'database' => 0,
        ],
    ],
];
