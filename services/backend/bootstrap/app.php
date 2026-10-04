<?php
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Http\Request;
use Symfony\Component\HttpKernel\Exception\HttpExceptionInterface;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(api: __DIR__.'/../routes/api.php')
    ->withSchedule(function (\Illuminate\Console\Scheduling\Schedule $schedule): void {
        $schedule->command('analyses:reconcile')->everyThirtySeconds();
    })
    ->withMiddleware(function (Middleware $middleware): void {
        // Browser traffic is same-origin through the loopback edge.
        $middleware->remove(Illuminate\Http\Middleware\HandleCors::class);
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        $exceptions->shouldRenderJsonWhen(fn () => true);
        $exceptions->render(function (\Throwable $error, Request $request) {
            if (!$request->is('api/analyses*')) {
                return null;
            }
            $notFound = $error instanceof HttpExceptionInterface && $error->getStatusCode() === 404;
            return response()->json([
                'schema_version' => 1,
                'error' => [
                    'code' => $notFound ? 'analysis_not_found' : 'internal_error',
                    'message' => $notFound ? 'Analysis not found.' : 'Internal application error.',
                    'details' => [],
                ],
            ], $notFound ? 404 : 500);
        });
    })->create();
