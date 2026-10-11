from app.rag.chunking import split_text
from app.rag.pipeline import RagPipeline, document_id
from app.rag.prompts import build_messages, format_documents, retrieval_query
from app.rag.types import RetrievedChunk
from tests.conftest import FakeEmbedder, FakeGenerator, FakeStore


def test_split_text_short_input_is_one_chunk():
    assert split_text("Hello world.") == ["Hello world."]
    assert split_text("   \n\n  ") == []


def test_split_text_respects_size_and_overlaps():
    text = " ".join(f"Sentence number {i} ends here." for i in range(200))
    chunks = split_text(text, chunk_size=300, overlap=60)
    assert len(chunks) > 5
    assert all(len(c) <= 300 for c in chunks)
    # Each chunk opens with text carried over from the end of the previous one.
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        assert cur[:20] in prev
    # Nothing is lost: every sentence appears in some chunk.
    assert all(any(f"number {i} ends" in c for c in chunks) for i in range(200))


def test_split_text_handles_text_without_separators():
    chunks = split_text("x" * 1000, chunk_size=300, overlap=50)
    assert all(len(c) <= 300 for c in chunks)
    assert sum(len(c) for c in chunks) >= 1000


def test_format_documents_numbers_sources_and_pages():
    chunks = [
        RetrievedChunk(id="a", text="alpha", source="a.pdf", page=3, score=0.9),
        RetrievedChunk(id="b", text="beta", source="b.txt", page=None, score=0.8),
    ]
    out = format_documents(chunks)
    assert '<document index="1" source="a.pdf" page="3">\nalpha\n</document>' in out
    assert '<document index="2" source="b.txt">\nbeta\n</document>' in out
    assert "no documents were retrieved" in format_documents([])


def test_build_messages_does_not_mutate_history():
    history = [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "q1"}]
    messages = build_messages("q2", history, [])
    assert len(history) == 2
    assert [m["role"] for m in messages] == ["user", "user"]


def test_retrieval_query_adds_previous_user_turn():
    assert retrieval_query("why?", []) == "why?"
    history = [{"role": "user", "content": "pricing"}, {"role": "assistant", "content": "..."}]
    assert retrieval_query("why?", history) == "pricing\nwhy?"


class ReverseReranker:
    """Scores the last candidate highest, to prove reranking reorders results."""

    def score(self, query, passages):
        return [float(i) for i in range(len(passages))]


def test_retrieve_reranks_and_truncates():
    store = FakeStore()
    pipeline = RagPipeline(
        embedder=FakeEmbedder(),
        store=store,
        generator=FakeGenerator(),
        reranker=ReverseReranker(),
        top_k=3,
        top_n=2,
        chunk_size=30,
        chunk_overlap=0,
    )
    pipeline.ingest(
        "notes.md",
        b"apples are red fruit.\n\nbananas are yellow fruit.\n\ncherries are small fruit.",
    )
    assert len(store.records) == 3

    plain = store.query(FakeEmbedder().embed_query("fruit"), 3)
    reranked = pipeline.retrieve("fruit")
    assert len(reranked) == 2
    assert reranked[0].id == plain[-1].id
    assert reranked[0].score == 2.0


def test_ingest_strips_directories_from_filename():
    store = FakeStore()
    pipeline = RagPipeline(embedder=FakeEmbedder(), store=store, generator=FakeGenerator())
    result = pipeline.ingest("../../etc/notes.txt", b"hello there")
    assert result.filename == "notes.txt"
    assert result.doc_id == document_id("notes.txt")
