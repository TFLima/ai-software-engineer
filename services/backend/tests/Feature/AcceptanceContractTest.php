<?php

namespace Tests\Feature;

use App\Analysis\EnvelopeValidator;
use PHPUnit\Framework\TestCase;

/** Python-produced pinned public fixture, checked without database/provider access. */
final class AcceptanceContractTest extends TestCase
{
    private function fixture(): array
    {
        return json_decode(file_get_contents(__DIR__.'/../Fixtures/b13-success.json'), true, 32, JSON_THROW_ON_ERROR);
    }

    private function request(array $result): array
    {
        $policy = require __DIR__.'/../../config/analysis.php';
        return [...array_intersect_key($result, array_flip(['analysis_id', 'attempt_id', 'repository', 'commit_sha'])),
            'selection_policy_version' => '1', 'context_policy_version' => '1', 'prompt_version' => '1',
            'limits' => $policy['limits']];
    }

    public function test_pinned_python_envelope_crosses_independent_php_validation(): void
    {
        $result = $this->fixture();
        $validated = (new EnvelopeValidator)->validate(json_encode($result, JSON_THROW_ON_ERROR), 200, $this->request($result));
        self::assertSame('7fd1a60b01f91b314f59955a4e4d4e80d8edf11d', $validated['commit_sha']);
        self::assertSame([['path' => 'README', 'start_line' => 1, 'end_line' => 1]], $validated['findings'][0]['evidence']);
        self::assertSame(1, $validated['coverage']['included_lines']);
    }

    public function test_evidence_tampering_rejects_whole_envelope(): void
    {
        $result = $this->fixture();
        $request = $this->request($result);
        $result['findings'][0]['evidence'][0]['end_line'] = 2;
        $this->expectException(\DomainException::class);
        (new EnvelopeValidator)->validate(json_encode($result, JSON_THROW_ON_ERROR), 200, $request);
    }
}
