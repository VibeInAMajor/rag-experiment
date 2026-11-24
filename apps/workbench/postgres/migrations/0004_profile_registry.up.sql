CREATE TABLE workbench.retrieval_profile_revisions (
    profile_id text NOT NULL CHECK (profile_id ~ '^[A-Za-z0-9_-]{1,128}$'),
    profile_revision text NOT NULL CHECK (profile_revision ~ '^[A-Za-z0-9_-]{1,128}$'),
    definition jsonb NOT NULL CHECK (jsonb_typeof(definition)='object'),
    policy_hash text NOT NULL CHECK (policy_hash ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(profile_id,profile_revision),
    UNIQUE(profile_id,profile_revision,policy_hash),
    CHECK (definition->>'profile_id'=profile_id AND definition->>'profile_revision'=profile_revision)
);

CREATE TABLE workbench.retrieval_profile_rollouts (
    workspace_id text NOT NULL REFERENCES workbench.workspaces(workspace_id),
    profile_id text NOT NULL,
    profile_revision text NOT NULL,
    policy_hash text NOT NULL,
    state text NOT NULL CHECK (state IN ('draft','qualified','active','retired')),
    rollout_version bigint NOT NULL CHECK (rollout_version>=1),
    qualified_generation_id bigint,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(workspace_id,profile_id),
    FOREIGN KEY(profile_id,profile_revision,policy_hash)
      REFERENCES workbench.retrieval_profile_revisions(profile_id,profile_revision,policy_hash),
    FOREIGN KEY(workspace_id,qualified_generation_id)
      REFERENCES workbench.index_generations(workspace_id,generation_id),
    CHECK (state NOT IN ('qualified','active') OR qualified_generation_id IS NOT NULL)
);

CREATE TABLE workbench.profile_rollout_events (
    workspace_id text NOT NULL REFERENCES workbench.workspaces(workspace_id),
    profile_id text NOT NULL,
    profile_revision text NOT NULL,
    policy_hash text NOT NULL,
    state text NOT NULL CHECK (state IN ('draft','qualified','active','retired')),
    rollout_version bigint NOT NULL CHECK (rollout_version>=1),
    qualified_generation_id bigint,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    event_id text NOT NULL DEFAULT gen_random_uuid()::text,
    PRIMARY KEY(workspace_id,profile_id,rollout_version),
    FOREIGN KEY(profile_id,profile_revision,policy_hash)
      REFERENCES workbench.retrieval_profile_revisions(profile_id,profile_revision,policy_hash),
    FOREIGN KEY(workspace_id,qualified_generation_id)
      REFERENCES workbench.index_generations(workspace_id,generation_id)
);

CREATE FUNCTION workbench.prevent_profile_history_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'Profile revision and rollout history are immutable';
END;
$$;
CREATE TRIGGER immutable_profile_revision BEFORE UPDATE OR DELETE ON workbench.retrieval_profile_revisions
FOR EACH ROW EXECUTE FUNCTION workbench.prevent_profile_history_mutation();
CREATE TRIGGER immutable_profile_rollout_event BEFORE UPDATE OR DELETE ON workbench.profile_rollout_events
FOR EACH ROW EXECUTE FUNCTION workbench.prevent_profile_history_mutation();

CREATE FUNCTION workbench.record_profile_rollout() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    IF TG_OP='INSERT' AND NEW.rollout_version<>1 THEN
        RAISE EXCEPTION 'Initial profile rollout version must be one';
    END IF;
    IF TG_OP='UPDATE' AND (
      NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR NEW.profile_id IS DISTINCT FROM OLD.profile_id
      OR NEW.rollout_version<>OLD.rollout_version+1) THEN
        RAISE EXCEPTION 'Invalid profile rollout transition';
    END IF;
    INSERT INTO workbench.profile_rollout_events(
      workspace_id,profile_id,profile_revision,policy_hash,state,rollout_version,qualified_generation_id)
    VALUES(NEW.workspace_id,NEW.profile_id,NEW.profile_revision,NEW.policy_hash,NEW.state,
      NEW.rollout_version,NEW.qualified_generation_id);
    RETURN NEW;
END;
$$;
CREATE TRIGGER record_profile_rollout AFTER INSERT OR UPDATE ON workbench.retrieval_profile_rollouts
FOR EACH ROW EXECUTE FUNCTION workbench.record_profile_rollout();

INSERT INTO workbench.retrieval_profile_revisions(profile_id,profile_revision,definition,policy_hash)
VALUES('postgres-fts-baseline','postgres-fts-baseline-r1',
'{"candidate_k":50,"capability_requirements":["schema","source_generation","lexical_index"],"capacity_policy_id":null,"chunk_profile_revision":null,"composition":"postgres_fts","dense_candidate_k":null,"dimensions":null,"filtering_policy":"workspace_active_version","index_dimensions":null,"index_generation_selector":"current","kind":"lexical","label":"PostgreSQL keyword search","lexical_candidate_k":null,"max_concurrent":2,"max_corpus_bytes":52428800,"max_corpus_chunks":10000,"max_query_characters":4096,"max_top_k":50,"model_profile_id":null,"model_profile_revision":null,"normalization":null,"parser_profile_revision":null,"processing_policy_hash":null,"profile_id":"postgres-fts-baseline","profile_revision":"postgres-fts-baseline-r1","rrf_k":null,"score_direction":"higher_is_better","score_type":"postgres_ts_rank_cd","timeout_ms":10000,"vector_representation":null,"workspace_ids":["development"]}'::jsonb,
'f4855098f89769756f443f6534b21c5a5f6fa039192e18b3fc7e7ec44b12676d');

INSERT INTO workbench.retrieval_profile_rollouts(
  workspace_id,profile_id,profile_revision,policy_hash,state,rollout_version,qualified_generation_id)
SELECT w.workspace_id,d.profile_id,d.profile_revision,d.policy_hash,'active',1,s.generation_id
FROM workbench.workspaces w JOIN workbench.corpus_index_state s USING(workspace_id)
CROSS JOIN workbench.retrieval_profile_revisions d
WHERE w.workspace_id='development' AND d.profile_id='postgres-fts-baseline'
 AND d.profile_revision='postgres-fts-baseline-r1';

CREATE FUNCTION workbench.initialize_profile_rollout() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NEW.workspace_id='development' THEN
      INSERT INTO workbench.retrieval_profile_rollouts(
        workspace_id,profile_id,profile_revision,policy_hash,state,rollout_version,qualified_generation_id)
      SELECT NEW.workspace_id,profile_id,profile_revision,policy_hash,'active',1,0
      FROM workbench.retrieval_profile_revisions WHERE profile_id='postgres-fts-baseline'
       AND profile_revision='postgres-fts-baseline-r1';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER initialize_profile_rollout AFTER INSERT ON workbench.workspaces
FOR EACH ROW EXECUTE FUNCTION workbench.initialize_profile_rollout();

ALTER TABLE workbench.retrieval_profile_rollouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.retrieval_profile_rollouts FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.retrieval_profile_rollouts
 USING(workspace_id=current_setting('workbench.workspace_id',true));
ALTER TABLE workbench.profile_rollout_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.profile_rollout_events FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.profile_rollout_events
 USING(workspace_id=current_setting('workbench.workspace_id',true));
REVOKE ALL ON workbench.retrieval_profile_revisions,workbench.retrieval_profile_rollouts,
 workbench.profile_rollout_events FROM PUBLIC;
REVOKE ALL ON FUNCTION workbench.prevent_profile_history_mutation(),workbench.record_profile_rollout(),
 workbench.initialize_profile_rollout() FROM PUBLIC;
