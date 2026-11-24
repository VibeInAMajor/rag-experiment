DROP TABLE workbench.ingestion_jobs;
DROP FUNCTION workbench.validate_ingestion_transition();
DELETE FROM workbench.schema_migrations WHERE revision='0002';
