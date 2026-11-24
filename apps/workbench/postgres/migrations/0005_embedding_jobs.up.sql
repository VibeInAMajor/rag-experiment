CREATE TABLE workbench.embedding_model_profiles (
 workspace_id text NOT NULL REFERENCES workbench.workspaces(workspace_id) ON DELETE CASCADE,
 profile_id text NOT NULL,
 profile_revision text NOT NULL,
 profile_fingerprint text NOT NULL CHECK(profile_fingerprint ~ '^[a-f0-9]{64}$'),
 dimensions integer NOT NULL CHECK(dimensions BETWEEN 32 AND 2560),
 definition jsonb NOT NULL CHECK(jsonb_typeof(definition)='object'),
 enabled boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,profile_id,profile_revision),
 UNIQUE(workspace_id,profile_fingerprint),
 UNIQUE(workspace_id,profile_fingerprint,dimensions),
 CHECK(definition->>'profile_id'=profile_id AND definition->>'profile_revision'=profile_revision
   AND (definition->>'dimensions')::integer=dimensions)
);
CREATE FUNCTION workbench.immutable_embedding_profile() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF (to_jsonb(NEW)-'enabled') IS DISTINCT FROM (to_jsonb(OLD)-'enabled') THEN
   RAISE EXCEPTION 'Embedding profile revisions are immutable';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER immutable_embedding_profile BEFORE UPDATE ON workbench.embedding_model_profiles
FOR EACH ROW EXECUTE FUNCTION workbench.immutable_embedding_profile();

CREATE TABLE workbench.embedding_jobs (
 workspace_id text NOT NULL,
 job_id text NOT NULL DEFAULT gen_random_uuid()::text,
 source_id text NOT NULL,
 version_id text NOT NULL,
 profile_id text NOT NULL,
 profile_revision text NOT NULL,
 profile_fingerprint text NOT NULL,
 status text NOT NULL DEFAULT 'queued'
  CHECK(status IN ('queued','running','retryable_failed','completed','stale','poisoned')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
 cursor text,
 owner_token text,
 lease_expires_at timestamptz,
 lease_seconds integer NOT NULL DEFAULT 120 CHECK(lease_seconds BETWEEN 10 AND 600),
 available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 error_code text CHECK(error_code IS NULL OR error_code ~ '^[A-Z0-9_]{1,64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,job_id),
 UNIQUE(workspace_id,source_id,version_id,profile_fingerprint),
 FOREIGN KEY(workspace_id,source_id,version_id)
  REFERENCES workbench.source_versions(workspace_id,source_id,version_id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,profile_id,profile_revision)
  REFERENCES workbench.embedding_model_profiles(workspace_id,profile_id,profile_revision),
 FOREIGN KEY(workspace_id,profile_fingerprint)
  REFERENCES workbench.embedding_model_profiles(workspace_id,profile_fingerprint),
 CHECK((status='running')=(owner_token IS NOT NULL AND lease_expires_at IS NOT NULL))
);
CREATE INDEX embedding_jobs_admission ON workbench.embedding_jobs(workspace_id,profile_fingerprint,status,available_at);

CREATE TABLE workbench.embedding_vectors (
 workspace_id text NOT NULL,
 profile_fingerprint text NOT NULL,
 processing_digest text NOT NULL CHECK(processing_digest ~ '^[a-f0-9]{64}$'),
 input_hash text NOT NULL CHECK(input_hash ~ '^[a-f0-9]{64}$'),
 dimensions integer NOT NULL,
 vector public.vector NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,profile_fingerprint,processing_digest,input_hash),
 FOREIGN KEY(workspace_id,profile_fingerprint,dimensions)
  REFERENCES workbench.embedding_model_profiles(workspace_id,profile_fingerprint,dimensions),
 CHECK(public.vector_dims(vector)=dimensions AND abs(public.vector_norm(vector)-1.0)<=0.001)
);
CREATE FUNCTION workbench.immutable_embedding_vector() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 RAISE EXCEPTION 'Cached embedding vectors are immutable';
END;
$$;
CREATE TRIGGER immutable_embedding_vector BEFORE UPDATE ON workbench.embedding_vectors
FOR EACH ROW EXECUTE FUNCTION workbench.immutable_embedding_vector();

ALTER TABLE workbench.chunks ADD CONSTRAINT chunks_embedding_reference UNIQUE(workspace_id,chunk_id,source_id,version_id);
CREATE TABLE workbench.chunk_embeddings (
 workspace_id text NOT NULL,
 chunk_id text NOT NULL,
 source_id text NOT NULL,
 version_id text NOT NULL,
 profile_fingerprint text NOT NULL,
 processing_digest text NOT NULL,
 input_hash text NOT NULL,
 expected_content_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,chunk_id,profile_fingerprint),
 FOREIGN KEY(workspace_id,chunk_id,source_id,version_id)
  REFERENCES workbench.chunks(workspace_id,chunk_id,source_id,version_id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,profile_fingerprint,processing_digest,input_hash)
  REFERENCES workbench.embedding_vectors(workspace_id,profile_fingerprint,processing_digest,input_hash) ON DELETE CASCADE
);
CREATE INDEX chunk_embeddings_source ON workbench.chunk_embeddings(workspace_id,source_id,version_id,profile_fingerprint);

CREATE TABLE workbench.embedding_generations (
 workspace_id text NOT NULL,
 profile_fingerprint text NOT NULL,
 index_generation bigint NOT NULL,
 eligible_active_chunks bigint NOT NULL CHECK(eligible_active_chunks>0),
 ready_embeddings bigint NOT NULL,
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,profile_fingerprint,index_generation),
 FOREIGN KEY(workspace_id,profile_fingerprint)
  REFERENCES workbench.embedding_model_profiles(workspace_id,profile_fingerprint),
 FOREIGN KEY(workspace_id,index_generation)
  REFERENCES workbench.index_generations(workspace_id,generation_id),
 CHECK(ready_embeddings=eligible_active_chunks)
);
CREATE TRIGGER immutable_embedding_generation BEFORE UPDATE ON workbench.embedding_generations
FOR EACH ROW EXECUTE FUNCTION workbench.immutable_embedding_vector();

CREATE FUNCTION workbench.schedule_source_embeddings() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE scope text; source text; version text; active boolean;
BEGIN
 scope:=CASE WHEN TG_OP='DELETE' THEN OLD.workspace_id ELSE NEW.workspace_id END;
 source:=CASE WHEN TG_OP='DELETE' THEN OLD.source_id ELSE NEW.source_id END;
 version:=CASE WHEN TG_OP='DELETE' THEN OLD.version_id ELSE NEW.version_id END;
 IF TG_TABLE_NAME='chunks' AND TG_OP<>'INSERT' THEN
   DELETE FROM workbench.chunk_embeddings WHERE workspace_id=scope AND chunk_id=OLD.chunk_id;
 END IF;
 SELECT EXISTS(SELECT 1 FROM workbench.source_versions v WHERE v.workspace_id=scope
  AND v.source_id=source AND v.version_id=version AND v.status='active') INTO active;
 IF NOT active THEN
   UPDATE workbench.embedding_jobs SET status='stale',owner_token=NULL,lease_expires_at=NULL,
    updated_at=clock_timestamp() WHERE workspace_id=scope AND source_id=source AND version_id=version;
 ELSE
   IF TG_TABLE_NAME='source_versions' AND TG_OP='UPDATE' AND OLD.metadata IS DISTINCT FROM NEW.metadata THEN
     DELETE FROM workbench.chunk_embeddings WHERE workspace_id=scope AND source_id=source AND version_id=version;
   END IF;
   INSERT INTO workbench.embedding_jobs(workspace_id,source_id,version_id,profile_id,profile_revision,profile_fingerprint)
   SELECT scope,source,version,p.profile_id,p.profile_revision,p.profile_fingerprint
    FROM workbench.embedding_model_profiles p WHERE p.workspace_id=scope AND p.enabled
   ON CONFLICT(workspace_id,source_id,version_id,profile_fingerprint) DO UPDATE
    SET status='queued',cursor=NULL,owner_token=NULL,lease_expires_at=NULL,attempts=0,error_code=NULL,
     available_at=clock_timestamp(),updated_at=clock_timestamp();
 END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER schedule_version_embeddings AFTER INSERT OR UPDATE OR DELETE ON workbench.source_versions
FOR EACH ROW EXECUTE FUNCTION workbench.schedule_source_embeddings();
CREATE TRIGGER schedule_chunk_embeddings AFTER INSERT OR UPDATE OR DELETE ON workbench.chunks
FOR EACH ROW EXECUTE FUNCTION workbench.schedule_source_embeddings();

DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['embedding_model_profiles','embedding_jobs','embedding_vectors','chunk_embeddings','embedding_generations']
 LOOP
  EXECUTE format('ALTER TABLE workbench.%I ENABLE ROW LEVEL SECURITY',item);
  EXECUTE format('ALTER TABLE workbench.%I FORCE ROW LEVEL SECURITY',item);
  EXECUTE format('CREATE POLICY workspace_scope ON workbench.%I USING(workspace_id=current_setting(''workbench.workspace_id'',true)) WITH CHECK(workspace_id=current_setting(''workbench.workspace_id'',true))',item);
  EXECUTE format('REVOKE ALL ON workbench.%I FROM PUBLIC',item);
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION workbench.immutable_embedding_profile(),workbench.immutable_embedding_vector(),
 workbench.schedule_source_embeddings() FROM PUBLIC;
