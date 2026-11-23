WITH corpus_rows AS (
 SELECT 'workspaces' AS table_name,to_jsonb(t)::text AS row_data FROM workbench.workspaces t
 UNION ALL SELECT 'sources',to_jsonb(t)::text FROM workbench.sources t
 UNION ALL SELECT 'source_versions',to_jsonb(t)::text FROM workbench.source_versions t
 UNION ALL SELECT 'chunks',to_jsonb(t)::text FROM workbench.chunks t
 UNION ALL SELECT 'embedding_profiles',to_jsonb(t)::text FROM workbench.embedding_profiles t
 UNION ALL SELECT 'ingestion_jobs',to_jsonb(t)::text FROM workbench.ingestion_jobs t
), signatures AS (
 SELECT table_name,count(*) AS row_count,encode(sha256(convert_to(string_agg(row_data,E'\n' ORDER BY row_data COLLATE "C"),'UTF8')),'hex') AS sha256
 FROM corpus_rows GROUP BY table_name
)
SELECT jsonb_object_agg(table_name,jsonb_build_object('row_count',row_count,'sha256',sha256)) FROM signatures;
