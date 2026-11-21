"""Local Workbench boundary with payload tracing and telemetry disabled."""

import os

os.environ["HAYSTACK_TELEMETRY_ENABLED"] = "false"
os.environ["HAYSTACK_CONTENT_TRACING_ENABLED"] = "false"

from apps.workbench.api.application import create_app
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.services import ReadinessProbe, ReadinessSnapshot

__all__ = ["ApiSettings", "ReadinessProbe", "ReadinessSnapshot", "create_app"]
