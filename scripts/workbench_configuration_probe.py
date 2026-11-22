"""Read-only configuration rollout evidence; credentials, YAML bodies and cookies are never retained."""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from apps.workbench.api.contracts import ConfigurationDocumentResponse
from apps.workbench.api.document_processing import validate_document_processing_yaml
from scripts.workbench_ingestion_probe import _database_snapshot

_DIRECTORY = Path("tasks/evidence/configuration-editor-2026-11-22")


def main() -> None:
    """Snapshot the live deployment without editing configuration, corpus or service processes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=("before", "pending", "after-restart", "after-conflict", "restored", "direct-access")
    )
    args = parser.parse_args()
    destination = _DIRECTORY / f"{args.phase}.json"
    if destination.exists():
        raise SystemExit("Evidence already exists; refusing to overwrite it.")
    dsn = os.environ.get("WORKBENCH_DB_DSN")
    if not dsn:
        raise SystemExit("Application database is required.")
    database = _database_snapshot(dsn)
    if args.phase != "before":
        original = json.loads((_DIRECTORY / "before.json").read_text(encoding="utf-8"))
        if database != original["database"]:
            raise SystemExit("The corpus changed during the configuration-only check.")
    with httpx.Client(
        base_url="http://127.0.0.1:8011", headers={"Origin": "http://127.0.0.1:4173"}, trust_env=False, timeout=10
    ) as client:
        anonymous = client.get("/api/v1/configuration")
        if anonymous.status_code != 403 or "yaml" in anonymous.json():
            raise SystemExit("Local application request-intent protection failed.")
        response = client.get("/api/v1/configuration", headers={"X-Workbench-Request": "configuration"})
        if response.status_code != 200:
            raise SystemExit("Configuration read failed.")
        document = ConfigurationDocumentResponse.model_validate(response.json())
        saved = validate_document_processing_yaml(document.yaml)
    report = {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "scope": "configuration-only local HTTP and read-only application-role SQL",
        "anonymous_read_status": anonymous.status_code,
        "access_policy": "trusted_local_application_no_login",
        "request_id": document.request_id,
        "trace_id": document.trace_id,
        "revision": document.revision,
        "yaml_sha256": hashlib.sha256(document.yaml.encode()).hexdigest(),
        "exists": document.exists,
        "activation": document.activation,
        "saved_profile": saved.safe_manifest(),
        "database": database,
        "corpus_unchanged": True,
    }
    _DIRECTORY.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": args.phase,
                "activation": document.activation,
                "anonymous_read_status": anonymous.status_code,
                "sources": database["source_count"],
                "chunks": database["chunk_count"],
                "corpus_unchanged": True,
            }
        )
    )


if __name__ == "__main__":
    main()
