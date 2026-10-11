import hashlib
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import PurePath
from typing import Protocol

from .chunking import split_text
from .loaders import DocumentError, load_document
from .prompts import SYSTEM_PROMPT, build_messages
from .types import Finished, IngestResult, RetrievedChunk, TextDelta, VectorRecord


class EmbedderLike(Protocol):
    def embed_query(self, text: str) -> list[float]: ...
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class RerankerLike(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


class VectorStoreLike(Protocol):
    def upsert(self, records: list[VectorRecord]) -> None: ...
    def query(self, vector: list[float], top_k: int) -> list[RetrievedChunk]: ...
    def delete_document(self, doc_id: str) -> int: ...


class GeneratorLike(Protocol):
    def stream(
        self, system: str, messages: list[dict[str, str]]
    ) -> AsyncIterator[TextDelta | Finished]: ...


def document_id(filename: str) -> str:
    """Stable id derived from the file name, so re-uploading a file replaces it."""
    return hashlib.sha256(filename.encode()).hexdigest()[:16]


class RagPipeline:
    def __init__(
        self,
        *,
        embedder: EmbedderLike,
        store: VectorStoreLike,
        generator: GeneratorLike,
        reranker: RerankerLike | None = None,
        top_k: int = 20,
        top_n: int = 5,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._generator = generator
        self._reranker = reranker
        self._top_k = top_k
        self._top_n = top_n
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    # The embedding, reranking and Pinecone calls below block; call them from a worker thread.

    def ingest(self, filename: str, data: bytes) -> IngestResult:
        filename = PurePath(filename).name
        pieces: list[tuple[int | None, str]] = [
            (page, piece)
            for page, text in load_document(filename, data)
            for piece in split_text(text, self._chunk_size, self._chunk_overlap)
        ]
        if not pieces:
            raise DocumentError("No extractable text found in the document")

        vectors = self._embedder.embed_documents([text for _, text in pieces])
        doc_id = document_id(filename)
        records = []
        for i, ((page, text), values) in enumerate(zip(pieces, vectors, strict=True)):
            metadata = {"doc_id": doc_id, "source": filename, "chunk": i, "text": text}
            if page is not None:
                metadata["page"] = page
            records.append(VectorRecord(id=f"{doc_id}#{i:05d}", values=values, metadata=metadata))

        # Drop the previous version first so a shorter re-upload leaves no stale chunks.
        self._store.delete_document(doc_id)
        self._store.upsert(records)
        return IngestResult(doc_id=doc_id, filename=filename, chunks=len(records))

    def delete_document(self, doc_id: str) -> int:
        return self._store.delete_document(doc_id)

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        candidates = self._store.query(self._embedder.embed_query(query), self._top_k)
        if self._reranker and candidates:
            scores = self._reranker.score(query, [c.text for c in candidates])
            ranked = sorted(zip(scores, candidates, strict=True), key=lambda p: p[0], reverse=True)
            candidates = [replace(chunk, score=float(score)) for score, chunk in ranked]
        return candidates[: self._top_n]

    def generate(
        self, question: str, history: list[dict[str, str]], chunks: list[RetrievedChunk]
    ) -> AsyncIterator[TextDelta | Finished]:
        return self._generator.stream(SYSTEM_PROMPT, build_messages(question, history, chunks))
