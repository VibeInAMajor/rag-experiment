CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

CREATE TABLE workbench.schema_migrations (
    revision text PRIMARY KEY,
    checksum text NOT NULL CHECK (checksum ~ '^[a-f0-9]{64}$'),
    tool_version text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE workbench.workspaces (
    workspace_id text PRIMARY KEY CHECK (workspace_id ~ '^[A-Za-z0-9_-]{1,128}$'),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE workbench.sources (
    workspace_id text NOT NULL,
    source_id text NOT NULL CHECK (source_id ~ '^[A-Za-z0-9_-]{1,128}$'),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 500),
    media_type text NOT NULL DEFAULT 'text/plain',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, source_id),
    FOREIGN KEY (workspace_id) REFERENCES workbench.workspaces (workspace_id) ON DELETE CASCADE
);

CREATE TABLE workbench.source_versions (
    workspace_id text NOT NULL,
    source_id text NOT NULL,
    version_id text NOT NULL CHECK (version_id ~ '^[A-Za-z0-9_-]{1,128}$'),
    status text NOT NULL DEFAULT 'staged' CHECK (status IN ('staged', 'active', 'superseded', 'error')),
    content_hash text NOT NULL CHECK (length(content_hash) BETWEEN 1 AND 128),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, source_id, version_id),
    FOREIGN KEY (workspace_id, source_id) REFERENCES workbench.sources (workspace_id, source_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX source_versions_one_active ON workbench.source_versions (workspace_id, source_id)
    WHERE status = 'active';

CREATE TABLE workbench.embedding_profiles (
    profile_id text PRIMARY KEY CHECK (profile_id ~ '^[A-Za-z0-9_-]{1,128}$'),
    dimensions integer NOT NULL CHECK (dimensions BETWEEN 1 AND 16000),
    enabled boolean NOT NULL DEFAULT false,
    purpose text NOT NULL CHECK (purpose IN ('synthetic', 'semantic')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    UNIQUE (profile_id, dimensions)
);

INSERT INTO workbench.embedding_profiles (profile_id, dimensions, enabled, purpose, metadata)
VALUES ('synthetic-test-v1', 3, true, 'synthetic', '{"development_only":true,"not_model_output":true}'::jsonb);

CREATE TABLE workbench.chunks (
    workspace_id text NOT NULL,
    chunk_id text NOT NULL CHECK (chunk_id ~ '^[A-Za-z0-9_-]{1,128}$'),
    source_id text NOT NULL,
    version_id text NOT NULL,
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 500),
    content text NOT NULL CHECK (length(content) BETWEEN 1 AND 32768),
    page integer CHECK (page > 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    content_hash text NOT NULL CHECK (length(content_hash) BETWEEN 1 AND 128),
    embedding public.vector,
    embedding_profile_id text,
    dimensions integer,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, content)) STORED,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, chunk_id),
    FOREIGN KEY (workspace_id, source_id, version_id)
        REFERENCES workbench.source_versions (workspace_id, source_id, version_id) ON DELETE CASCADE,
    FOREIGN KEY (embedding_profile_id, dimensions)
        REFERENCES workbench.embedding_profiles (profile_id, dimensions),
    CHECK (
        (embedding IS NULL AND embedding_profile_id IS NULL AND dimensions IS NULL)
        OR (embedding IS NOT NULL AND embedding_profile_id IS NOT NULL AND dimensions IS NOT NULL
            AND public.vector_dims(embedding) = dimensions)
    )
);

CREATE INDEX chunks_source_version ON workbench.chunks (workspace_id, source_id, version_id);
CREATE INDEX chunks_search_vector ON workbench.chunks USING gin (search_vector);

ALTER TABLE workbench.workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.workspaces FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.workspaces
    USING (workspace_id = current_setting('workbench.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('workbench.workspace_id', true));

ALTER TABLE workbench.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.sources FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.sources
    USING (workspace_id = current_setting('workbench.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('workbench.workspace_id', true));

ALTER TABLE workbench.source_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.source_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.source_versions
    USING (workspace_id = current_setting('workbench.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('workbench.workspace_id', true));

ALTER TABLE workbench.chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.chunks FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.chunks
    USING (workspace_id = current_setting('workbench.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('workbench.workspace_id', true));

REVOKE ALL ON SCHEMA workbench FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA workbench FROM PUBLIC;
