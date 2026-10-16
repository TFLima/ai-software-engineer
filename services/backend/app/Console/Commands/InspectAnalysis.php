<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

final class InspectAnalysis extends Command
{
    protected $signature = 'analyses:inspect {id}';
    protected $description = 'Show safe status, queue age, attempt timings, errors and token usage';

    public function handle(): int
    {
        $id = $this->argument('id');
        if (!is_string($id) || !preg_match('/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/D', $id)) {
            $this->error('Invalid analysis ID.');
            return self::FAILURE;
        }
        $row = DB::table('analyses')->where('id', $id)->first();
        if (!$row) {
            $this->error('Analysis not found.');
            return self::FAILURE;
        }
        $attempts = DB::table('analysis_attempts')->where('analysis_id', $id)->orderBy('attempt_number')->get()
            ->map(function ($attempt): array {
                $provenance = $attempt->provenance ? json_decode($attempt->provenance, true, 32, JSON_THROW_ON_ERROR) : null;
                return ['attempt_id' => $attempt->id, 'number' => $attempt->attempt_number,
                    'status' => $attempt->status, 'error_code' => $attempt->error_code,
                    'error_stage' => $attempt->error_stage,
                    'stage_durations_ms' => $attempt->stage_durations_ms ? json_decode($attempt->stage_durations_ms, true, 32, JSON_THROW_ON_ERROR) : null,
                    'usage' => $provenance['usage'] ?? null];
            });
        $this->line(json_encode(['analysis_id' => $id, 'status' => $row->status,
            'queue_age_seconds' => $row->status === 'queued'
                ? max(0, (int) Carbon::parse($row->next_attempt_at ?? $row->created_at)->diffInSeconds(now(), false)) : null,
            'error_code' => $row->error_code, 'attempts' => $attempts], JSON_THROW_ON_ERROR | JSON_PRETTY_PRINT));
        return self::SUCCESS;
    }
}
