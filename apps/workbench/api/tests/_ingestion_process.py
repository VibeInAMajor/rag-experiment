"""Disposable-only subprocess fixture; no pause hook exists in the production application."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Literal

import uvicorn
from psycopg.conninfo import conninfo_to_dict

from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.persistence.models import IngestionJob, WorkspaceContext
from apps.workbench.postgres.postgres import PostgresPersistence


class _PausingRepository(PostgresPersistence):
    def __init__(self, dsn: str, *, marker: Path) -> None:
        super().__init__(dsn)
        self._marker = marker

    async def transition_ingestion(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        stage: Literal["parsing", "chunking", "publishing"],
    ) -> IngestionJob:
        job = await super().transition_ingestion(context, job_id=job_id, owner_token=owner_token, stage=stage)
        if stage == "parsing":
            marker = json.dumps({"job_id": job.job_id, "status": job.status, "stage": job.stage})
            await asyncio.to_thread(self._marker.write_text, marker, encoding="utf-8")
            await asyncio.Event().wait()
        return job


def main() -> None:
    """Run one real API process only against a fixture-owned UUID database and an unrelated loopback port."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    dsn = os.environ.get("WORKBENCH_DB_DSN", "")
    name = conninfo_to_dict(dsn).get("dbname", "")
    if (
        not isinstance(name, str)
        or not name.startswith("rag_test_")
        or args.port in (8010, 8011, 4173)
        or not 1024 <= args.port <= 65535
    ):
        raise SystemExit("The process fixture requires a disposable database and isolated port.")
    marker = Path(os.environ["WORKBENCH_INGESTION_PROCESS_MARKER"])
    repository = _PausingRepository(dsn, marker=marker)
    application = create_app(settings=ApiSettings(port=args.port), persistence=repository)
    server = uvicorn.Server(
        uvicorn.Config(
            application, host="127.0.0.1", port=args.port, access_log=False, log_level="warning", loop="asyncio"
        )
    )
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        runner.run(server.serve())


if __name__ == "__main__":
    main()
