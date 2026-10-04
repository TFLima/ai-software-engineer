<?php

namespace App\Analysis;

use App\Support\StrictJson;

/** Validate authenticated boundary metadata; never repair/drop fields. */
final class EnvelopeValidator
{
    public function validate(string $body, int $status, array $request): ?array
    {
        $root = StrictJson::decodeTree($body);
        // An identified response from a different invocation is ignored, even if otherwise invalid.
        if ((isset($root->analysis_id) && $root->analysis_id !== $request['analysis_id'])
            || (isset($root->attempt_id) && $root->attempt_id !== $request['attempt_id'])) {
            return null;
        }
        if (!property_exists($root, 'outcome')) {
            $this->object($root, ['schema_version', 'error']);
            $this->require($root->schema_version === 1);
            $this->object($root->error, ['code', 'stage', 'retryable']);
            $code = $root->error->code;
            $this->require($root->error->stage === 'request' && $root->error->retryable === false);
            $valid = match ($code) {
                'invalid_request' => in_array($status, [400, 413, 415, 422], true),
                'unsupported_schema' => $status === 422,
                'unauthorized_internal' => $status === 401,
                default => false,
            };
            $this->require($valid);
            return ['outcome' => 'failed', 'error' => ['code' => $code, 'stage' => 'request', 'retryable' => false],
                'commit_sha' => $request['commit_sha'], 'coverage' => null, 'provenance' => null, 'stage_durations_ms' => null];
        }
        $success = $root->outcome === 'succeeded';
        $this->require($success || $root->outcome === 'failed');
        $fields = ['schema_version', 'finding_schema_version', 'analysis_id', 'attempt_id', 'outcome', 'repository', 'commit_sha', 'coverage', 'provenance', 'stage_durations_ms'];
        $this->object($root, [...$fields, $success ? 'findings' : 'error']);
        $this->require($root->schema_version === 1 && $root->finding_schema_version === 1
            && $root->analysis_id === $request['analysis_id'] && $root->attempt_id === $request['attempt_id']);
        $this->object($root->repository, ['owner', 'name', 'url']);
        foreach (['owner', 'name', 'url'] as $key) {
            $this->require($root->repository->$key === $request['repository'][$key]);
        }
        $this->require(($root->commit_sha === null && !$success)
            || (is_string($root->commit_sha) && preg_match('/\A[0-9a-f]{40}\z/D', $root->commit_sha)));
        $this->require($request['commit_sha'] === null || $request['commit_sha'] === $root->commit_sha);
        $limits = $request['limits'];
        if ($root->coverage !== null) {
            $this->coverage($root->coverage, $limits, $success);
            $this->require($root->commit_sha !== null);
        } else {
            $this->require(!$success);
        }
        if ($root->provenance !== null) {
            $p = $root->provenance;
            $this->object($p, ['finding_schema_version', 'selection_policy_version', 'context_policy_version', 'prompt_version', 'provider', 'model', 'usage']);
            $this->require($p->finding_schema_version === 1);
            foreach (['selection_policy_version', 'context_policy_version', 'prompt_version'] as $key) {
                $this->require($p->$key === $request[$key]);
            }
            $this->text($p->provider, 128, false);
            $this->text($p->model, 128, false);
            $this->object($p->usage, ['input_tokens', 'output_tokens']);
            foreach (['input_tokens', 'output_tokens'] as $key) {
                $this->require($p->usage->$key === null || $this->integer($p->usage->$key, 0, $limits[$key] * $limits['operation_tries']));
            }
        } else {
            $this->require(!$success);
        }
        $this->object($root->stage_durations_ms, ['acquire', 'select', 'context', 'generate', 'validate', 'cleanup']);
        foreach ((array) $root->stage_durations_ms as $key => $duration) {
            $this->require(($duration === null && !$success) || $this->integer($duration, 0, $limits[$key.'_seconds'] * 1000));
        }
        $this->require(array_sum((array) $root->stage_durations_ms) <= $limits['overall_seconds'] * 1000);
        if ($success) {
            $this->require($status === 200 && is_array($root->findings) && count($root->findings) <= $limits['max_findings']);
            foreach ($root->findings as $finding) {
                $this->finding($finding, $root->coverage->included_spans, $limits);
            }
        } else {
            $e = $root->error;
            $this->object($e, ['code', 'stage', 'retryable']);
            $this->require(in_array($e->code, [...Policy::TERMINAL, ...array_diff(Policy::TRANSIENT, ['queue_unavailable', 'attempt_expired'])], true));
            $this->require($e->retryable === in_array($e->code, Policy::TRANSIENT, true));
            $this->require(in_array($e->stage, ['request', 'acquire', 'select', 'context', 'generate', 'validate', 'cleanup'], true));
            $statuses = match ($e->code) {
                'network_unavailable' => [502], 'upstream_unavailable' => [502, 503],
                'upstream_timeout' => [504], 'upstream_rate_limited' => [429],
                'invalid_result', 'configuration_error' => [500],
                default => [422],
            };
            $this->require(in_array($status, $statuses, true));
            $this->require($status !== 503 || $e->stage === 'request');
        }
        return json_decode(json_encode($root, JSON_THROW_ON_ERROR), true, 32, JSON_THROW_ON_ERROR);
    }

    private function coverage(mixed $c, array $limits, bool $success): void
    {
        $this->object($c, ['inventory_files', 'eligible_files', 'included_files', 'included_lines', 'omitted_files', 'included_spans', 'omissions', 'limitations']);
        foreach (['inventory_files', 'eligible_files', 'included_files', 'omitted_files'] as $key) {
            $this->require($this->integer($c->$key, 0, $limits['file_count']));
        }
        $this->require(is_int($c->included_lines) && $c->included_lines >= 0
            && $c->included_files <= $c->eligible_files && $c->eligible_files <= $c->inventory_files
            && $c->omitted_files === $c->inventory_files - $c->included_files);
        $this->require(is_array($c->included_spans) && count($c->included_spans) <= $limits['context_spans']);
        $previous = null;
        $lines = 0;
        $paths = [];
        foreach ($c->included_spans as $span) {
            $this->span($span, $limits);
            if ($previous) {
                $this->require(strcmp($previous->path, $span->path) < 0
                    || ($previous->path === $span->path && $span->start_line > $previous->end_line + 1));
            }
            $previous = $span;
            $lines += $span->end_line - $span->start_line + 1;
            $paths[$span->path] = true;
        }
        $this->require($lines === $c->included_lines && count($paths) === $c->included_files && count($paths) <= $limits['context_files']);
        $this->require(!$success || ($lines > 0 && count($paths) > 0));
        $this->require(is_array($c->omissions) && count($c->omissions) <= 16);
        $seen = [];
        $omitted = 0;
        foreach ($c->omissions as $omission) {
            $this->object($omission, ['reason', 'files']);
            $this->require(in_array($omission->reason, ['binary', 'generated', 'vendor', 'sensitive', 'unsupported_text', 'context_budget', 'submodule', 'lfs'], true)
                && !isset($seen[$omission->reason]) && $this->integer($omission->files, 0, $limits['file_count']));
            $seen[$omission->reason] = true;
            $omitted += $omission->files;
        }
        $this->require($omitted === $c->omitted_files && is_array($c->limitations) && count($c->limitations) >= 1 && count($c->limitations) <= 16);
        foreach ($c->limitations as $text) {
            $this->text($text, 256);
        }
    }

    private function finding(mixed $finding, array $spans, array $limits): void
    {
        $this->object($finding, ['category', 'severity', 'title', 'explanation', 'recommendation', 'evidence'], ['confidence']);
        $this->require(in_array($finding->category, ['architecture', 'maintainability', 'reliability', 'security', 'testing'], true)
            && in_array($finding->severity, ['info', 'low', 'medium', 'high', 'critical'], true));
        $finding->title = $this->text($finding->title, 160, false);
        $finding->explanation = $this->text($finding->explanation, 4000);
        $finding->recommendation = $this->text($finding->recommendation, 2000);
        if (property_exists($finding, 'confidence')) {
            $this->require((is_int($finding->confidence) || is_float($finding->confidence))
                && is_finite((float) $finding->confidence) && $finding->confidence >= 0 && $finding->confidence <= 1);
        }
        $this->require(is_array($finding->evidence) && count($finding->evidence) >= 1 && count($finding->evidence) <= $limits['evidence_per_finding']);
        $seen = [];
        foreach ($finding->evidence as $evidence) {
            $this->span($evidence, $limits);
            $identity = json_encode($evidence, JSON_THROW_ON_ERROR);
            $this->require(!isset($seen[$identity]));
            $seen[$identity] = true;
            $included = false;
            foreach ($spans as $span) {
                $included = $included || ($span->path === $evidence->path && $span->start_line <= $evidence->start_line && $span->end_line >= $evidence->end_line);
            }
            $this->require($included);
        }
    }

    private function span(mixed $span, array $limits): void
    {
        $this->object($span, ['path', 'start_line', 'end_line']);
        $this->text($span->path, $limits['path_characters'], false);
        $this->require(!preg_match('/[\\\\\x00-\x1f\x7f]/', $span->path) && !preg_match('/\A[A-Za-z]:/', $span->path));
        $segments = explode('/', $span->path);
        $this->require(count($segments) <= $limits['path_depth'] && !array_intersect($segments, ['', '.', '..']));
        $this->require($this->integer($span->start_line, 1, PHP_INT_MAX) && $this->integer($span->end_line, $span->start_line, PHP_INT_MAX));
    }

    private function object(mixed $object, array $required, array $optional = []): void
    {
        $this->require($object instanceof \stdClass);
        $keys = array_keys((array) $object);
        $this->require(!array_diff($required, $keys) && !array_diff($keys, [...$required, ...$optional]));
    }

    private function text(mixed $text, int $maximum, bool $multiline = true): string
    {
        $this->require(is_string($text) && !preg_match($multiline ? '/[\x00-\x08\x0b-\x1f\x7f]/u' : '/[\x00-\x1f\x7f]/u', $text));
        $trimmed = preg_replace('/\A\s+|\s+\z/u', '', $text);
        $this->require(mb_strlen($trimmed) >= 1 && mb_strlen($trimmed) <= $maximum);
        return $trimmed;
    }

    private function integer(mixed $number, int $minimum, int $maximum): bool
    {
        return is_int($number) && $number >= $minimum && $number <= $maximum;
    }

    private function require(bool $condition): void
    {
        if (!$condition) {
            throw new \DomainException('Invalid internal result');
        }
    }
}
