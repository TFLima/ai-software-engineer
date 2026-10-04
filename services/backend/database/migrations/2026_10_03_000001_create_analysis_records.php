<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('analyses', function (Blueprint $table): void {
            $table->uuid('id')->primary();
            $table->string('idempotency_key', 128)->unique();
            $table->char('request_hash', 64);
            $table->string('repository_owner', 39);
            $table->string('repository_name', 100);
            $table->string('repository_url', 160);
            $table->string('status', 16);
            $table->char('commit_sha', 40)->nullable();
            $table->unsignedSmallInteger('attempt_count')->default(0);
            $table->uuid('active_attempt_id')->nullable();
            $table->timestampTz('next_attempt_at')->nullable();
            $table->timestampTz('started_at')->nullable();
            $table->timestampTz('finished_at')->nullable();
            $table->jsonb('coverage')->nullable();
            $table->jsonb('provenance')->nullable();
            $table->string('error_code', 64)->nullable();
            $table->string('error_stage', 16)->nullable();
            $table->timestampsTz();
            $table->index(['status', 'next_attempt_at', 'created_at']);
            $table->index('created_at');
        });

        Schema::create('analysis_attempts', function (Blueprint $table): void {
            $table->uuid('id')->primary();
            $table->foreignUuid('analysis_id')->constrained('analyses')->cascadeOnDelete();
            $table->unsignedSmallInteger('attempt_number');
            $table->string('status', 16);
            $table->timestampTz('deadline_at');
            $table->timestampTz('lease_expires_at');
            $table->char('commit_sha', 40)->nullable();
            $table->string('selection_policy_version', 32);
            $table->string('context_policy_version', 32);
            $table->string('prompt_version', 32);
            $table->unsignedSmallInteger('finding_schema_version');
            $table->jsonb('effective_limits');
            $table->jsonb('coverage')->nullable();
            $table->jsonb('provenance')->nullable();
            $table->jsonb('stage_durations_ms')->nullable();
            $table->string('error_code', 64)->nullable();
            $table->string('error_stage', 16)->nullable();
            $table->timestampTz('finished_at')->nullable();
            $table->timestampsTz();
            $table->unique(['analysis_id', 'attempt_number']);
            $table->unique(['analysis_id', 'id']);
        });

        Schema::create('findings', function (Blueprint $table): void {
            $table->uuid('id')->primary();
            $table->foreignUuid('analysis_id')->constrained('analyses')->cascadeOnDelete();
            $table->uuid('attempt_id');
            $table->foreign(['analysis_id', 'attempt_id'])->references(['analysis_id', 'id'])->on('analysis_attempts')->cascadeOnDelete();
            $table->unsignedSmallInteger('ordinal');
            $table->string('category', 32);
            $table->string('severity', 16);
            $table->string('title', 160);
            $table->text('explanation');
            $table->text('recommendation');
            $table->jsonb('evidence');
            $table->double('confidence')->nullable();
            $table->timestampsTz();
            $table->unique(['attempt_id', 'ordinal']);
            $table->index(['analysis_id', 'ordinal']);
        });

        DB::statement("ALTER TABLE analyses ADD CONSTRAINT analyses_status_check CHECK (status IN ('queued', 'running', 'completed', 'failed'))");
        DB::statement('ALTER TABLE analyses ADD CONSTRAINT analyses_attempt_count_check CHECK (attempt_count BETWEEN 0 AND 3)');
        DB::statement("ALTER TABLE analyses ADD CONSTRAINT analyses_active_check CHECK ((status = 'running') = (active_attempt_id IS NOT NULL))");
        DB::statement("ALTER TABLE analysis_attempts ADD CONSTRAINT attempts_status_check CHECK (status IN ('running', 'succeeded', 'failed', 'expired'))");
        DB::statement('ALTER TABLE analysis_attempts ADD CONSTRAINT attempts_number_check CHECK (attempt_number BETWEEN 1 AND 3)');
        DB::statement('ALTER TABLE findings ADD CONSTRAINT findings_ordinal_check CHECK (ordinal BETWEEN 0 AND 19)');
        DB::statement('ALTER TABLE findings ADD CONSTRAINT findings_confidence_check CHECK (confidence BETWEEN 0 AND 1)');
    }

    public function down(): void
    {
        Schema::dropIfExists('findings');
        Schema::dropIfExists('analysis_attempts');
        Schema::dropIfExists('analyses');
    }
};
