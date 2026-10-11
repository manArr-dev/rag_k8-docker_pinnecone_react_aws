from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    text: str
    source: str
    page: int | None
    score: float


@dataclass(frozen=True)
class VectorRecord:
    id: str
    values: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class IngestResult:
    doc_id: str
    filename: str
    chunks: int


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Finished:
    stop_reason: str | None
    model: str
    input_tokens: int
    output_tokens: int
