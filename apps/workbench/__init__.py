"""Local Workbench modules with payload tracing and telemetry disabled."""

import os

os.environ["HAYSTACK_TELEMETRY_ENABLED"] = "false"
os.environ["HAYSTACK_CONTENT_TRACING_ENABLED"] = "false"
