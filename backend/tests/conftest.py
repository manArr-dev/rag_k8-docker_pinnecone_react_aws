import hashlib
import math
import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.rag.pipeline import RagPipeline
from app.rag.types import Finished, RetrievedChunk, TextDelta

DIM = 64


class FakeEmbedder:
    """Bag-of-words hashing embedder: texts sharing words get similar vectors."""

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        for word in re.findall(r"\w+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_query(self, text):
        return self._embed(text)

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]


class FakeStore:
    def __init__(self):
        self.records = {}

    def upsert(self, records):
        for r in records:
            self.records[r.id] = r

    def query(self, vector, top_k):
        scored = sorted(
            (
                (sum(a * b for a, b in zip(vector, r.values, strict=True)), r)
                for r in self.records.values()
            ),
            key=lambda p: p[0],
            reverse=True,
        )
        return [
            RetrievedChunk(
                id=r.id,
                text=r.metadata["text"],
                source=r.metadata["source"],
                page=r.metadata.get("page"),
                score=score,
            )
            for score, r in scored[:top_k]
        ]

    def delete_document(self, doc_id):
        ids = [i for i in self.records if i.startswith(f"{doc_id}#")]
        for i in ids:
            del self.records[i]
        return len(ids)


class FakeGenerator:
    def __init__(self):
        self.calls = []
        self.stop_reason = "end_turn"
        self.error = None

    async def stream(self, system, messages):
        self.calls.append((system, messages))
        if self.error:
            raise self.error
        for word in ("Paris ", "[1]"):
            yield TextDelta(word)
        yield Finished(stop_reason=self.stop_reason, model="fake", input_tokens=10, output_tokens=2)


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def generator():
    return FakeGenerator()


def make_client(store, generator, **settings_overrides):
    settings = Settings(_env_file=None, **settings_overrides)
    pipeline = RagPipeline(
        embedder=FakeEmbedder(), store=store, generator=generator, top_k=5, top_n=2
    )
    return TestClient(create_app(pipeline=pipeline, settings=settings))


@pytest.fixture
def client(store, generator):
    with make_client(store, generator, admin_api_key="secret") as c:
        yield c
