"""Local, construction-only Haystack pipeline validation."""

import os

# This isolated tool must never send telemetry or initialize telemetry configuration.
os.environ["HAYSTACK_TELEMETRY_ENABLED"] = "false"

__all__: list[str] = []
