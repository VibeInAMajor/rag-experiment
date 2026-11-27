"""An application-owned registration for one typed agent entry point."""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentDefinition:
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    instructions: str
    prompt_revision: str
    output_schema_revision: str
    required_capabilities: frozenset[str] = frozenset({"structured_output", "reasoning"})
    allowed_profiles: frozenset[str] | None = None
    validate_output: Callable[[BaseModel, BaseModel], BaseModel] | None = None
