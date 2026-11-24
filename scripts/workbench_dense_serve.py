"""Explicit local Dense HTTP launcher using the existing attested model and one measured admission runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import uvicorn
import yaml

from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.embedding.embedding import EmbeddingError
from apps.workbench.persistence.models import PersistenceError, WorkspaceContext
from apps.workbench.retrieval.dense import DenseService
from apps.workbench.retrieval.profile_registry import ProfileRegistry, default_profile_registry
from apps.workbench.retrieval.profiles import dense_profile_definition
from scripts.workbench_embedding_backfill import load_capacity_configuration, open_backfill_runtime


async def _serve(args: argparse.Namespace) -> None:
    settings = ApiSettings.from_env()
    if settings.database_dsn is None:
        raise ValueError("EXPLICIT_DATABASE_CONFIGURATION_REQUIRED")
    async with open_backfill_runtime(
        dsn=settings.database_dsn.get_secret_value(),
        model_directory=args.model_directory,
        capacity_config=args.capacity_config,
        context=WorkspaceContext(workspace_id="development"),
        endpoint=args.endpoint,
        container=args.container,
        processing=settings.document_processing,
    ) as runtime:

        async def readiness() -> None:
            await runtime.governor.check_ready_async()
            await runtime.adapter.check_ready_async()

        dense = DenseService(
            runtime.persistence,
            embedding=runtime.adapter,
            profile=runtime.profile,
            counter=runtime.counter,
            registry=settings.profile_registry,
            readiness=readiness,
            capacity_policy_id=runtime.capacity.policy_id,
        )
        application = create_app(settings=settings, persistence=runtime.persistence, dense=dense)
        server = uvicorn.Server(
            uvicorn.Config(application, host=settings.host, port=args.port or settings.port, access_log=False)
        )
        await server.serve()


def main() -> int:
    """Start only an explicit measured runtime; migrations, backfill and profile activation stay separate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capacity-config", type=Path, required=True)
    parser.add_argument("--model-directory", type=Path, default=Path("A:/AI/TEI/qwen3-4b"))
    parser.add_argument("--endpoint", default="http://127.0.0.1:8082")
    parser.add_argument("--container", default="rag-workbench-embedding-1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--write-profile-registry", type=Path)
    args = parser.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        if args.write_profile_registry is not None:
            profile, capacity = load_capacity_configuration(args.capacity_config)
            definition = dense_profile_definition(profile, capacity_policy_id=capacity.policy_id)
            registry = ProfileRegistry(profiles=(*default_profile_registry().profiles, definition))
            with args.write_profile_registry.open("x", encoding="utf-8") as destination:
                yaml.safe_dump(registry.model_dump(mode="json"), destination, allow_unicode=True, sort_keys=False)
            print(json.dumps({"status": "REGISTRY_WRITTEN", "runtime_qualified": False}))
            return 0
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None) as runner:
            runner.run(_serve(args))
    except (EmbeddingError, PersistenceError, ValueError, OSError):
        print(json.dumps({"status": "UNAVAILABLE", "code": "DENSE_RUNTIME_UNAVAILABLE"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
