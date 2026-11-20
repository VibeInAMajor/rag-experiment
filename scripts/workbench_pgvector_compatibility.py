"""Probe the pinned optional integration on an owned disposable database only."""

import json
import logging
import os
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import psycopg
from haystack_integrations.components.retrievers.pgvector import PgvectorEmbeddingRetriever, PgvectorKeywordRetriever
from haystack_integrations.document_stores.pgvector import PgvectorDocumentStore
from psycopg import sql
from psycopg.conninfo import make_conninfo

from haystack import Document
from haystack.utils import Secret


def main() -> None:
    """Measure package compatibility without sharing its tables with the application."""
    admin_dsn = os.environ.get("WORKBENCH_DB_ADMIN_DSN")
    app_dsn = os.environ.get("WORKBENCH_DB_DSN")
    if not admin_dsn or not app_dsn:
        raise SystemExit("Load the explicit development administrator environment first.")
    database = f"rag_compat_{uuid4().hex}"
    control_dsn = make_conninfo(admin_dsn, dbname="postgres")
    admin_store = None
    restricted_store = None
    logging.getLogger("haystack_integrations.document_stores.pgvector.document_store").disabled = True
    with psycopg.connect(control_dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    try:
        admin_store = PgvectorDocumentStore(
            connection_string=Secret.from_token(make_conninfo(admin_dsn, dbname=database)),
            embedding_dimension=3,
            language="simple",
            search_strategy="exact_nearest_neighbor",
        )
        written = admin_store.write_documents(
            [
                Document(id="lease", content="Lease renewal ERR-LEASE-204", embedding=[1.0, 0.0, 0.0]),
                Document(id="backup", content="Database backup retention", embedding=[0.0, 1.0, 0.0]),
            ]
        )
        lexical = PgvectorKeywordRetriever(document_store=admin_store).run(query="ERR-LEASE-204")
        dense = PgvectorEmbeddingRetriever(document_store=admin_store).run(query_embedding=[1.0, 0.0, 0.0])
        assert written == 2 and lexical["documents"][0].id == "lease" and dense["documents"][0].id == "lease"
        restricted_store = PgvectorDocumentStore(
            connection_string=Secret.from_token(make_conninfo(app_dsn, dbname=database)),
            create_extension=False,
            table_name="restricted_probe",
            embedding_dimension=3,
            language="simple",
        )
        refused = False
        try:
            restricted_store.count_documents()
        except Exception:
            refused = True
        assert refused
        report = {
            "haystack_version": version("haystack-ai"),
            "integration_version": version("pgvector-haystack"),
            "disposable_write_count": written,
            "keyword_expected_source_first": True,
            "synthetic_vector_expected_source_first": True,
            "restricted_role_implicit_ddl_refused": refused,
            "selected_application_adapter": "app_owned_sql",
            "reasons": [
                "integration owns a flat id-primary-key document table with JSON metadata",
                "application requires composite workspace/source/version foreign keys and forced RLS",
                "integration initializes table/index DDL instead of using the migration-owned chunk contract",
                "a second integration-owned table would duplicate the application corpus",
            ],
            "real_embedding_inference": "not_run",
        }
        destination = Path("tasks/evidence/pgvector-compatibility-2026-11-21.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
    finally:
        if restricted_store is not None:
            restricted_store.close()
        if admin_store is not None:
            admin_store.close()
        with psycopg.connect(control_dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


if __name__ == "__main__":
    main()
