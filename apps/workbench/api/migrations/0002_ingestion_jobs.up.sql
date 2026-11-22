CREATE TABLE workbench.ingestion_jobs (
    workspace_id text NOT NULL,
    job_id text NOT NULL CHECK (job_id ~ '^[A-Za-z0-9_-]{1,128}$'),
    reserved_source_id text NOT NULL CHECK (reserved_source_id ~ '^[A-Za-z0-9_-]{1,128}$'),
    source_id text,
    reserved_version_id text NOT NULL CHECK (reserved_version_id ~ '^[A-Za-z0-9_-]{1,128}$'),
    effective_version_id text,
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[A-Za-z0-9_-]{8,128}$'),
    request_fingerprint text NOT NULL CHECK (request_fingerprint ~ '^[a-f0-9]{64}$'),
    source_content_sha256 text NOT NULL CHECK (source_content_sha256 ~ '^[a-f0-9]{64}$'),
    processing_profile_fingerprint text CHECK (processing_profile_fingerprint ~ '^[a-f0-9]{64}$'),
    operation text NOT NULL CHECK (operation IN ('create', 'update')),
    expected_active_version_id text,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','parsing','chunking','publishing','completed','failed')),
    stage text NOT NULL DEFAULT 'pending' CHECK (stage IN ('pending','parsing','chunking','publishing','completed')),
    owner_token text NOT NULL CHECK (owner_token ~ '^[A-Za-z0-9_-]{1,128}$'),
    lock_key bigint NOT NULL,
    error_code text CHECK (error_code ~ '^[A-Z][A-Z0-9_]{0,63}$'),
    retryable boolean NOT NULL DEFAULT false,
    chunk_count integer CHECK (chunk_count BETWEEN 1 AND 10000),
    outcome text CHECK (outcome IN ('created','updated','unchanged')),
    corpus_revision text CHECK (corpus_revision ~ '^[A-Za-z0-9_-]{1,128}$'),
    stage_timings_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(stage_timings_jsonb)='array' AND jsonb_array_length(stage_timings_jsonb)<=3
               AND octet_length(stage_timings_jsonb::text)<=4096),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    PRIMARY KEY (workspace_id,job_id),
    UNIQUE (workspace_id,idempotency_key),
    FOREIGN KEY (workspace_id) REFERENCES workbench.workspaces (workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id,source_id) REFERENCES workbench.sources (workspace_id,source_id),
    FOREIGN KEY (workspace_id,source_id,effective_version_id)
        REFERENCES workbench.source_versions (workspace_id,source_id,version_id),
    CHECK (source_id IS NULL OR source_id=reserved_source_id),
    CHECK ((operation='create' AND expected_active_version_id IS NULL)
           OR (operation='update' AND source_id IS NOT NULL AND expected_active_version_id IS NOT NULL)),
    CHECK (
        (status IN ('pending','parsing','chunking','publishing') AND stage=status
            AND finished_at IS NULL AND error_code IS NULL AND outcome IS NULL
            AND effective_version_id IS NULL AND chunk_count IS NULL AND corpus_revision IS NULL)
        OR (status='failed' AND stage IN ('pending','parsing','chunking','publishing')
            AND finished_at IS NOT NULL AND error_code IS NOT NULL AND outcome IS NULL
            AND effective_version_id IS NULL AND chunk_count IS NULL AND corpus_revision IS NULL)
        OR (status='completed' AND stage='completed' AND finished_at IS NOT NULL
            AND error_code IS NULL AND NOT retryable AND outcome IS NOT NULL
            AND source_id IS NOT NULL AND effective_version_id IS NOT NULL
            AND chunk_count IS NOT NULL AND corpus_revision IS NOT NULL
            AND processing_profile_fingerprint IS NOT NULL)
    )
);

CREATE INDEX ingestion_jobs_source ON workbench.ingestion_jobs (workspace_id,source_id);
CREATE INDEX ingestion_jobs_reserved_source ON workbench.ingestion_jobs (workspace_id,reserved_source_id);
CREATE INDEX ingestion_jobs_unfinished ON workbench.ingestion_jobs (workspace_id,created_at)
    WHERE status NOT IN ('completed','failed');

ALTER TABLE workbench.ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.ingestion_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.ingestion_jobs
    USING (workspace_id=current_setting('workbench.workspace_id',true))
    WITH CHECK (workspace_id=current_setting('workbench.workspace_id',true));

CREATE FUNCTION workbench.validate_ingestion_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.workspace_id,NEW.job_id,NEW.reserved_source_id,NEW.reserved_version_id,NEW.idempotency_key,
        NEW.request_fingerprint,NEW.source_content_sha256,NEW.operation,NEW.expected_active_version_id,
        NEW.owner_token,NEW.lock_key,NEW.created_at)
        IS DISTINCT FROM
       (OLD.workspace_id,OLD.job_id,OLD.reserved_source_id,OLD.reserved_version_id,OLD.idempotency_key,
        OLD.request_fingerprint,OLD.source_content_sha256,OLD.operation,OLD.expected_active_version_id,
        OLD.owner_token,OLD.lock_key,OLD.created_at) THEN
        RAISE EXCEPTION 'Immutable ingestion reservation';
    END IF;
    IF OLD.status IN ('completed','failed') OR NOT (
        (OLD.status='pending' AND NEW.status IN ('parsing','failed'))
        OR (OLD.status='parsing' AND NEW.status IN ('chunking','failed'))
        OR (OLD.status='chunking' AND NEW.status IN ('publishing','failed'))
        OR (OLD.status='publishing' AND NEW.status IN ('completed','failed'))
    ) THEN
        RAISE EXCEPTION 'Invalid ingestion transition';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ingestion_transition BEFORE UPDATE ON workbench.ingestion_jobs
    FOR EACH ROW EXECUTE FUNCTION workbench.validate_ingestion_transition();
REVOKE ALL ON workbench.ingestion_jobs FROM PUBLIC;
REVOKE ALL ON FUNCTION workbench.validate_ingestion_transition() FROM PUBLIC;
