<?php

namespace App\Analysis;

use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

final class InternalClient
{
    public function run(array $request, Lifecycle $lifecycle): void
    {
        $limits = config('analysis.limits');
        $secret = config('analysis.internal_secret');
        if (!is_string($secret) || strlen($secret) < 32) {
            $lifecycle->fail($request, 'configuration_error', 'request');
            return;
        }
        if (strlen(json_encode($request, JSON_THROW_ON_ERROR)) > $limits['internal_body_bytes']) {
            $lifecycle->fail($request, 'configuration_error', 'request');
            return;
        }
        $start = hrtime(true);
        $stream = null;
        $result = null;
        $failure = null;
        try {
            $response = Http::withToken($secret)->acceptJson()->asJson()
                ->connectTimeout($limits['connect_seconds'])->timeout($limits['worker_http_seconds'])
                ->withOptions(['allow_redirects' => false, 'stream' => true, 'read_timeout' => $limits['connect_seconds']])
                ->post(rtrim(config('analysis.internal_url'), '/').'/internal/v1/analyses:run', $request);
            $stream = $response->toPsrResponse()->getBody();
            $body = '';
            while (!$stream->eof()) {
                if ((hrtime(true) - $start) / 1e9 >= $limits['worker_http_seconds']) {
                    throw new \OverflowException('Internal transport deadline');
                }
                $body .= $stream->read(min(8192, $request['limits']['internal_response_bytes'] + 1 - strlen($body)));
                if (strlen($body) > $request['limits']['internal_response_bytes']) {
                    throw new \DomainException('Invalid internal result');
                }
            }
            if (strtolower(trim(explode(';', $response->header('Content-Type'))[0])) !== 'application/json') {
                throw new \DomainException('Invalid internal result');
            }
            $result = app(EnvelopeValidator::class)->validate($body, $response->status(), $request);
            if ($result === null) {
                Log::notice('analysis_stale_response', ['analysis_id' => $request['analysis_id'], 'attempt_id' => $request['attempt_id']]);
            }
        } catch (ConnectionException $error) {
            $previous = $error->getPrevious();
            $context = $previous && method_exists($previous, 'getHandlerContext') ? $previous->getHandlerContext() : [];
            $failure = ($context['errno'] ?? null) === 28 ? 'upstream_timeout' : 'network_unavailable';
        } catch (\OverflowException) {
            $failure = 'upstream_timeout';
        } catch (\DomainException | \JsonException | \TypeError | \UnexpectedValueException) {
            $failure = 'invalid_result';
        } catch (\RuntimeException) {
            // Stream connection loss. Close/cancel the response; never resend the same POST.
            $failure = 'network_unavailable';
        } finally {
            $stream?->close();
        }
        // Persistence exceptions propagate to lease recovery; they are not transport failures.
        if ($failure !== null) {
            $lifecycle->fail($request, $failure, 'transport');
        } elseif ($result !== null) {
            $lifecycle->accept($request, $result);
        }
    }
}
