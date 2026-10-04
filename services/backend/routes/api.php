<?php
use App\Http\Controllers\AnalysisController;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Route;

Route::get('/health', function () {
    try {
        DB::select('SELECT 1');
        Redis::connection()->ping();
    } catch (Throwable) {
        return response()->json(['status' => 'unavailable', 'service' => 'application'], 503);
    }
    return response()->json(['status' => 'ok', 'service' => 'application']);
});

Route::post('/analyses', [AnalysisController::class, 'store']);
Route::get('/analyses/{id}', [AnalysisController::class, 'show']);
Route::get('/analyses/{id}/findings', [AnalysisController::class, 'findings']);
