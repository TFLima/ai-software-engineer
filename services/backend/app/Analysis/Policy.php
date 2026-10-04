<?php

namespace App\Analysis;

final class Policy
{
    public const TRANSIENT = ['network_unavailable', 'upstream_timeout', 'upstream_rate_limited', 'upstream_unavailable', 'attempt_expired', 'queue_unavailable'];
    public const TERMINAL = ['invalid_request', 'unsupported_schema', 'unauthorized_internal', 'repository_unavailable', 'unsafe_snapshot', 'limit_exceeded', 'no_eligible_context', 'invalid_findings', 'invalid_result', 'configuration_error'];

    public static function validate(array $limits): void
    {
        // Validate every central setting, including settings not sent to FastAPI.
        $defaults = (require base_path('config/analysis.php'))['limits'];
        if (array_diff_key($defaults, $limits) || array_diff_key($limits, $defaults)) {
            throw new \LogicException('Invalid analysis limits configuration');
        }
        foreach ($limits as $value) {
            if (!is_int($value) || $value <= 0) {
                throw new \LogicException('Invalid analysis limits configuration');
            }
        }
        $ordered = ['overall_seconds', 'worker_http_seconds', 'job_seconds', 'attempt_lease_seconds', 'redis_reservation_seconds'];
        for ($i = 1; $i < count($ordered); $i++) {
            if ($limits[$ordered[$i - 1]] >= $limits[$ordered[$i]]) {
                throw new \LogicException('Invalid analysis timeout ordering');
            }
        }
        if ($limits['automatic_attempts'] !== 2 || $limits['total_attempts'] !== 3 || $limits['active_analyses'] !== 1
            || $limits['operation_tries'] > 2 || $limits['max_findings'] > 20 || $limits['evidence_per_finding'] > 5
            || $limits['context_files'] > $limits['file_count'] || $limits['context_tokens'] > $limits['input_tokens']
            || $limits['attempt_tokens'] < $limits['operation_tries'] * ($limits['input_tokens'] + $limits['output_tokens'])
            || $limits['archive_bytes'] > $limits['download_bytes'] || $limits['file_bytes'] > $limits['extracted_bytes']
            || array_sum(array_intersect_key($limits, array_flip(['acquire_seconds', 'select_seconds', 'context_seconds', 'generate_seconds', 'validate_seconds', 'cleanup_seconds']))) > $limits['overall_seconds']) {
            throw new \LogicException('Inconsistent analysis limits');
        }
    }
}
