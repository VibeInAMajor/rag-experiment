LOCK TABLE workbench.workspaces,workbench.sources,workbench.source_versions,workbench.chunks IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE workbench.index_generations (
    workspace_id text NOT NULL REFERENCES workbench.workspaces(workspace_id) ON DELETE CASCADE,
    generation_id bigint NOT NULL CHECK (generation_id >= 0),
    corpus_id text NOT NULL,
    corpus_revision text NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    active_source_count bigint NOT NULL CHECK (active_source_count >= 0),
    active_chunk_count bigint NOT NULL CHECK (active_chunk_count >= 0),
    content_bytes bigint NOT NULL CHECK (content_bytes >= 0),
    active_source_manifest_hash text NOT NULL CHECK (active_source_manifest_hash ~ '^[a-f0-9]{64}$'),
    source_manifest_xor bit(256) NOT NULL DEFAULT repeat('0',256)::bit(256),
    lexical_index_revision text NOT NULL CHECK (lexical_index_revision = 'postgres-fts-baseline-r1'),
    status text NOT NULL CHECK (status = 'ready'),
    previous_generation bigint,
    event_id text NOT NULL,
    event_kind text NOT NULL CHECK (event_kind IN ('initial','backfill','publication','metadata','reconciliation')),
    PRIMARY KEY(workspace_id,generation_id),
    UNIQUE(workspace_id,corpus_revision),
    CHECK ((generation_id=0 AND previous_generation IS NULL) OR
           (generation_id>0 AND previous_generation=generation_id-1)),
    FOREIGN KEY(workspace_id,previous_generation) REFERENCES workbench.index_generations(workspace_id,generation_id)
);

CREATE TABLE workbench.corpus_index_state (LIKE workbench.index_generations INCLUDING DEFAULTS INCLUDING CONSTRAINTS);
ALTER TABLE workbench.corpus_index_state DROP CONSTRAINT index_generations_status_check;
ALTER TABLE workbench.corpus_index_state ADD CHECK (status IN ('ready','dirty'));
ALTER TABLE workbench.corpus_index_state ADD PRIMARY KEY(workspace_id);
ALTER TABLE workbench.corpus_index_state ADD FOREIGN KEY(workspace_id)
    REFERENCES workbench.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE workbench.corpus_index_state ADD FOREIGN KEY(workspace_id,generation_id)
    REFERENCES workbench.index_generations(workspace_id,generation_id);

CREATE TABLE workbench.corpus_source_state (
    workspace_id text NOT NULL,
    source_id text NOT NULL,
    version_id text NOT NULL,
    chunk_count bigint NOT NULL CHECK (chunk_count >= 0),
    content_bytes bigint NOT NULL CHECK (content_bytes >= 0),
    source_hash bit(256) NOT NULL,
    PRIMARY KEY(workspace_id,source_id),
    FOREIGN KEY(workspace_id,source_id) REFERENCES workbench.sources(workspace_id,source_id) ON DELETE CASCADE,
    FOREIGN KEY(workspace_id,source_id,version_id)
        REFERENCES workbench.source_versions(workspace_id,source_id,version_id)
);

CREATE FUNCTION workbench.index_source_projection(scope text, source text)
RETURNS TABLE(version_id text,chunk_count bigint,content_bytes bigint,source_hash bit(256))
LANGUAGE sql STABLE SET search_path=pg_catalog AS $$
    SELECT v.version_id,count(c.chunk_id),COALESCE(sum(octet_length(c.content)),0)::bigint,
      ('x'||encode(sha256(convert_to(
        (to_jsonb(s)-'updated_at'-'created_at')::text ||
        (to_jsonb(v)-'updated_at'-'created_at')::text ||
        COALESCE(bit_xor(('x'||encode(sha256(convert_to(
          (to_jsonb(c)-'search_vector'-'created_at')::text,'UTF8')),'hex'))::bit(256))::text,''),
        'UTF8')),'hex'))::bit(256)
    FROM workbench.sources s JOIN workbench.source_versions v USING(workspace_id,source_id)
    LEFT JOIN workbench.chunks c USING(workspace_id,source_id,version_id)
    WHERE s.workspace_id=scope AND s.source_id=source AND v.status='active'
    GROUP BY s.workspace_id,s.source_id,v.workspace_id,v.source_id,v.version_id;
$$;

CREATE FUNCTION workbench.initialize_corpus_index() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE root text := encode(sha256(convert_to(repeat('0',256),'UTF8')),'hex');
BEGIN
    INSERT INTO workbench.index_generations(
      workspace_id,generation_id,corpus_id,corpus_revision,active_source_count,active_chunk_count,
      content_bytes,active_source_manifest_hash,source_manifest_xor,lexical_index_revision,status,previous_generation,event_id,event_kind)
    VALUES(NEW.workspace_id,0,'corpus-'||encode(sha256(convert_to(NEW.workspace_id,'UTF8')),'hex'),
      'corpus-'||encode(sha256(convert_to(NEW.workspace_id||':0:'||root,'UTF8')),'hex'),
      0,0,0,root,repeat('0',256)::bit(256),'postgres-fts-baseline-r1','ready',NULL,gen_random_uuid()::text,'initial');
    INSERT INTO workbench.corpus_index_state SELECT * FROM workbench.index_generations
      WHERE workspace_id=NEW.workspace_id AND generation_id=0;
    RETURN NEW;
END;
$$;
CREATE TRIGGER initialize_corpus_index AFTER INSERT ON workbench.workspaces
FOR EACH ROW EXECUTE FUNCTION workbench.initialize_corpus_index();

CREATE FUNCTION workbench.mark_corpus_index_dirty() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE old_active boolean := false;
DECLARE new_active boolean := false;
BEGIN
    IF TG_TABLE_NAME='source_versions' THEN
        old_active := TG_OP <> 'INSERT' AND (to_jsonb(OLD)->>'status')='active';
        new_active := TG_OP <> 'DELETE' AND (to_jsonb(NEW)->>'status')='active';
    ELSE
        old_active := TG_OP <> 'INSERT' AND EXISTS(SELECT 1 FROM workbench.source_versions v
          WHERE v.workspace_id=OLD.workspace_id AND v.source_id=OLD.source_id AND v.status='active'
            AND (TG_TABLE_NAME<>'chunks' OR v.version_id=(to_jsonb(OLD)->>'version_id')));
        new_active := TG_OP <> 'DELETE' AND EXISTS(SELECT 1 FROM workbench.source_versions v
          WHERE v.workspace_id=NEW.workspace_id AND v.source_id=NEW.source_id AND v.status='active'
            AND (TG_TABLE_NAME<>'chunks' OR v.version_id=(to_jsonb(NEW)->>'version_id')));
    END IF;
    -- The same lock as publication prevents a later commit from clearing unrelated drift.
    PERFORM 1 FROM workbench.workspaces WHERE workspace_id IN (
      CASE WHEN old_active THEN OLD.workspace_id END,CASE WHEN new_active THEN NEW.workspace_id END)
      ORDER BY workspace_id COLLATE "C" FOR UPDATE;
    UPDATE workbench.corpus_index_state SET status='dirty' WHERE status<>'dirty' AND workspace_id IN (
      CASE WHEN old_active THEN OLD.workspace_id END,CASE WHEN new_active THEN NEW.workspace_id END);
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER dirty_source_index BEFORE INSERT OR UPDATE OR DELETE ON workbench.sources
FOR EACH ROW EXECUTE FUNCTION workbench.mark_corpus_index_dirty();
CREATE TRIGGER dirty_version_index AFTER INSERT OR UPDATE OR DELETE ON workbench.source_versions
FOR EACH ROW EXECUTE FUNCTION workbench.mark_corpus_index_dirty();
CREATE TRIGGER dirty_chunk_index AFTER INSERT OR UPDATE OR DELETE ON workbench.chunks
FOR EACH ROW EXECUTE FUNCTION workbench.mark_corpus_index_dirty();

CREATE FUNCTION workbench.commit_source_generation(scope text, source text, kind text DEFAULT 'publication')
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE old_source workbench.corpus_source_state%ROWTYPE;
DECLARE projected record;
DECLARE current_state workbench.corpus_index_state%ROWTYPE;
DECLARE aggregate_hash bit(256);
DECLARE root text;
BEGIN
    IF scope IS DISTINCT FROM current_setting('workbench.workspace_id',true)
       OR kind NOT IN ('publication','metadata','reconciliation') THEN
        RAISE EXCEPTION 'Invalid index publication scope';
    END IF;
    PERFORM 1 FROM workbench.workspaces WHERE workspace_id=scope FOR UPDATE;
    SELECT * INTO STRICT current_state FROM workbench.corpus_index_state WHERE workspace_id=scope FOR UPDATE;
    SELECT * INTO old_source FROM workbench.corpus_source_state WHERE workspace_id=scope AND source_id=source;
    SELECT * INTO projected FROM workbench.index_source_projection(scope,source);
    IF projected.version_id IS NULL THEN RAISE EXCEPTION 'No active source to publish'; END IF;
    IF old_source.source_hash IS NOT DISTINCT FROM projected.source_hash AND current_state.status='ready' THEN
        RETURN;
    END IF;
    INSERT INTO workbench.corpus_source_state(workspace_id,source_id,version_id,chunk_count,content_bytes,source_hash)
      VALUES(scope,source,projected.version_id,projected.chunk_count,projected.content_bytes,projected.source_hash)
      ON CONFLICT(workspace_id,source_id) DO UPDATE SET version_id=EXCLUDED.version_id,
        chunk_count=EXCLUDED.chunk_count,content_bytes=EXCLUDED.content_bytes,source_hash=EXCLUDED.source_hash;
    aggregate_hash := current_state.source_manifest_xor # COALESCE(old_source.source_hash,repeat('0',256)::bit(256)) # projected.source_hash;
    root := encode(sha256(convert_to(aggregate_hash::text,'UTF8')),'hex');
    INSERT INTO workbench.index_generations(
      workspace_id,generation_id,corpus_id,corpus_revision,active_source_count,active_chunk_count,
      content_bytes,active_source_manifest_hash,source_manifest_xor,lexical_index_revision,status,previous_generation,event_id,event_kind)
    VALUES(scope,current_state.generation_id+1,current_state.corpus_id,
      'corpus-'||encode(sha256(convert_to(scope||':'||(current_state.generation_id+1)::text||':'||root,'UTF8')),'hex'),
      current_state.active_source_count+CASE WHEN old_source.source_id IS NULL THEN 1 ELSE 0 END,
      current_state.active_chunk_count-COALESCE(old_source.chunk_count,0)+projected.chunk_count,
      current_state.content_bytes-COALESCE(old_source.content_bytes,0)+projected.content_bytes,
      root,aggregate_hash,current_state.lexical_index_revision,'ready',current_state.generation_id,gen_random_uuid()::text,kind);
    UPDATE workbench.corpus_index_state s SET (
      generation_id,corpus_id,corpus_revision,committed_at,active_source_count,active_chunk_count,content_bytes,
      active_source_manifest_hash,source_manifest_xor,lexical_index_revision,status,previous_generation,event_id,event_kind) = (
      SELECT generation_id,corpus_id,corpus_revision,committed_at,active_source_count,active_chunk_count,content_bytes,
      active_source_manifest_hash,source_manifest_xor,lexical_index_revision,status,previous_generation,event_id,event_kind
      FROM workbench.index_generations g WHERE g.workspace_id=scope AND g.generation_id=current_state.generation_id+1)
      WHERE s.workspace_id=scope;
END;
$$;

-- Backfill is a one-time migration under the migrator transaction/DDL locks.
INSERT INTO workbench.index_generations(
  workspace_id,generation_id,corpus_id,corpus_revision,active_source_count,active_chunk_count,
  content_bytes,active_source_manifest_hash,lexical_index_revision,status,event_id,event_kind)
SELECT workspace_id,0,'corpus-'||encode(sha256(convert_to(workspace_id,'UTF8')),'hex'),
 'corpus-'||encode(sha256(convert_to(workspace_id||':0:'||
   encode(sha256(convert_to(repeat('0',256),'UTF8')),'hex'),'UTF8')),'hex'),
 0,0,0,encode(sha256(convert_to(repeat('0',256),'UTF8')),'hex'),
 'postgres-fts-baseline-r1','ready',gen_random_uuid()::text,'initial' FROM workbench.workspaces;
INSERT INTO workbench.corpus_index_state SELECT * FROM workbench.index_generations;
INSERT INTO workbench.corpus_source_state
SELECT s.workspace_id,s.source_id,p.* FROM workbench.sources s
CROSS JOIN LATERAL workbench.index_source_projection(s.workspace_id,s.source_id) p;
INSERT INTO workbench.index_generations(
 workspace_id,generation_id,corpus_id,corpus_revision,active_source_count,active_chunk_count,
 content_bytes,active_source_manifest_hash,source_manifest_xor,lexical_index_revision,status,previous_generation,event_id,event_kind)
SELECT workspace_id,1,'corpus-'||encode(sha256(convert_to(workspace_id,'UTF8')),'hex'),
 'corpus-'||encode(sha256(convert_to(workspace_id||':1:'||root,'UTF8')),'hex'),
 source_count,chunk_count,bytes,root,manifest_xor,'postgres-fts-baseline-r1','ready',0,gen_random_uuid()::text,'backfill'
FROM (SELECT workspace_id,count(*) AS source_count,sum(chunk_count) AS chunk_count,sum(content_bytes) AS bytes,
 bit_xor(source_hash) AS manifest_xor,encode(sha256(convert_to(bit_xor(source_hash)::text,'UTF8')),'hex') AS root
 FROM workbench.corpus_source_state GROUP BY workspace_id) aggregate;
UPDATE workbench.corpus_index_state s SET (
 generation_id,corpus_revision,committed_at,active_source_count,active_chunk_count,content_bytes,
 active_source_manifest_hash,source_manifest_xor,previous_generation,event_id,event_kind) = (
 SELECT generation_id,corpus_revision,committed_at,active_source_count,active_chunk_count,content_bytes,
 active_source_manifest_hash,source_manifest_xor,previous_generation,event_id,event_kind FROM workbench.index_generations g
 WHERE g.workspace_id=s.workspace_id AND g.generation_id=1)
WHERE EXISTS(SELECT 1 FROM workbench.index_generations g WHERE g.workspace_id=s.workspace_id AND g.generation_id=1);

ALTER TABLE workbench.index_generations ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.index_generations FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.index_generations
 USING(workspace_id=current_setting('workbench.workspace_id',true));
ALTER TABLE workbench.corpus_index_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.corpus_index_state FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.corpus_index_state
 USING(workspace_id=current_setting('workbench.workspace_id',true));
ALTER TABLE workbench.corpus_source_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE workbench.corpus_source_state FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON workbench.corpus_source_state
 USING(workspace_id=current_setting('workbench.workspace_id',true));
REVOKE ALL ON workbench.index_generations,workbench.corpus_index_state,workbench.corpus_source_state FROM PUBLIC;
REVOKE ALL ON FUNCTION workbench.index_source_projection(text,text),workbench.initialize_corpus_index(),
 workbench.mark_corpus_index_dirty(),workbench.commit_source_generation(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION workbench.commit_source_generation(text,text,text) TO workbench_app;

CREATE FUNCTION workbench.prevent_index_generation_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'Committed index generations are immutable';
END;
$$;
CREATE TRIGGER immutable_index_generation BEFORE UPDATE OR DELETE ON workbench.index_generations
FOR EACH ROW EXECUTE FUNCTION workbench.prevent_index_generation_mutation();
REVOKE ALL ON FUNCTION workbench.prevent_index_generation_mutation() FROM PUBLIC;

CREATE FUNCTION workbench.validate_corpus_generation_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    IF NEW.generation_id < OLD.generation_id OR NEW.generation_id > OLD.generation_id+1
       OR NEW.corpus_id IS DISTINCT FROM OLD.corpus_id THEN
        RAISE EXCEPTION 'Invalid corpus generation transition';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER corpus_generation_transition BEFORE UPDATE ON workbench.corpus_index_state
FOR EACH ROW EXECUTE FUNCTION workbench.validate_corpus_generation_transition();
REVOKE ALL ON FUNCTION workbench.validate_corpus_generation_transition() FROM PUBLIC;



