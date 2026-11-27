"""An application-owned registration for one typed agent entry point."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel


class VerdictRejected(ValueError):
    """A verdict failed a local rule identified by a fixed diagnostic code."""

    def __init__(self, rule: StrEnum, *, message: str) -> None:
        super().__init__(message)
        self.rule = rule


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
