import json

from app.rag.generator import GenerationError
from tests.conftest import make_client

ADMIN = {"X-API-Key": "secret"}
DOC = (
    b"Paris is the capital of France and sits on the Seine.\n\n"
    b"Tokyo is the capital of Japan and its largest city."
)


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def upload(client, name="facts.txt", data=DOC, headers=ADMIN):
    return client.post("/api/documents", files={"file": (name, data)}, headers=headers)


def test_health_and_readiness(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}


def test_ingest_then_chat_streams_sources_and_answer(client, store, generator):
    res = upload(client)
    assert res.status_code == 200
    assert res.json()["chunks"] == len(store.records) >= 1

    res = client.post("/api/chat", json={"message": "What is the capital of France?"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(res.text)

    assert [name for name, _ in events] == ["sources", "token", "token", "done"]
    sources = events[0][1]["sources"]
    assert sources[0]["index"] == 1 and sources[0]["source"] == "facts.txt"
    assert "".join(d["text"] for name, d in events if name == "token") == "Paris [1]"
    assert events[-1][1] == {"truncated": False}

    # The retrieved text reaches the model inside the final user turn.
    _, messages = generator.calls[0]
    assert "Paris is the capital of France" in messages[-1]["content"]
    assert messages[-1]["content"].endswith("Question: What is the capital of France?")


def test_chat_passes_history_and_drops_leading_assistant_turn(client, generator):
    history = [
        {"role": "assistant", "content": "Hi, ask me anything."},
        {"role": "user", "content": "Tell me about France"},
        {"role": "assistant", "content": "France is in Europe."},
    ]
    client.post("/api/chat", json={"message": "And its capital?", "history": history})
    _, messages = generator.calls[0]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[0]["content"] == "Tell me about France"


def test_chat_reports_generation_errors_as_sse_event(client, generator):
    generator.error = GenerationError("The service is busy.")
    events = parse_sse(client.post("/api/chat", json={"message": "hi"}).text)
    assert events[-1] == ("error", {"message": "The service is busy."})


def test_chat_reports_refusal_and_truncation(client, generator):
    generator.stop_reason = "refusal"
    events = parse_sse(client.post("/api/chat", json={"message": "hi"}).text)
    assert events[-1][0] == "error"

    generator.stop_reason = "max_tokens"
    events = parse_sse(client.post("/api/chat", json={"message": "hi"}).text)
    assert events[-1] == ("done", {"truncated": True})


def test_chat_rejects_empty_message(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_reupload_replaces_previous_chunks(client, store):
    upload(client, data=DOC + b"\n\n" + b"Filler sentence about nothing. " * 200)
    assert len(store.records) > 1
    upload(client, data=b"Short replacement.")
    assert [r.metadata["text"] for r in store.records.values()] == ["Short replacement."]


def test_delete_document(client, store):
    doc_id = upload(client).json()["doc_id"]
    res = client.delete(f"/api/documents/{doc_id}", headers=ADMIN)
    assert res.json()["deleted_chunks"] >= 1
    assert store.records == {}


def test_document_endpoints_require_admin_key(client):
    assert upload(client, headers={}).status_code == 401
    assert upload(client, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.delete("/api/documents/abc").status_code == 401


def test_document_endpoints_closed_in_production_without_key(store, generator):
    with make_client(store, generator) as c:
        assert upload(c, headers={}).status_code == 403
    with make_client(store, generator, app_env="development") as c:
        assert upload(c, headers={}).status_code == 200


def test_upload_validation(store, generator):
    with make_client(store, generator, admin_api_key="secret", max_upload_mb=1) as c:
        assert upload(c, name="image.png", data=b"x").status_code == 422
        assert upload(c, data=b"   ").status_code == 422
        assert upload(c, data=b"\xff\xfe\x00bad").status_code == 422
        assert upload(c, data=b"a" * (1024 * 1024 + 1)).status_code == 413
