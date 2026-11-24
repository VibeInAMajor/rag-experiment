"""Exact dense query vector checks before entering SQL."""

from math import hypot, isfinite

from apps.workbench.embedding.embedding import EmbeddingProfile
from apps.workbench.persistence.models import InvalidEmbedding


def validate_query_vector(embedding: list[float], profile: EmbeddingProfile) -> None:
    """Reject incompatible query output before opening a database transaction."""
    if (
        len(embedding) != profile.dimensions
        or any(type(value) not in {float, int} or not isfinite(value) for value in embedding)
        or abs(hypot(*embedding) - 1.0) > 0.001
    ):
        raise InvalidEmbedding("The query vector must match the finite normalized embedding profile.")
