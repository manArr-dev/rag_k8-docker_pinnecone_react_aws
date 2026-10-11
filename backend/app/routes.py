import json
import logging
import secrets
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from .config import Settings
from .rag.generator import GenerationError
from .rag.loaders import DocumentError
from .rag.pipeline import RagPipeline
from .rag.prompts import retrieval_query
from .rag.types import Finished, TextDelta
from .schemas import ChatRequest, DeleteResponse, IngestResponse

logger = logging.getLogger(__name__)

health_router = APIRouter()
api_router = APIRouter(prefix="/api")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_pipeline(request: Request) -> RagPipeline:
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(503, "Service is starting")
    return pipeline


def require_admin(
    settings: Settings = Depends(get_settings),
    x_api_key: str | None = Header(default=None),
) -> None:
    expected = settings.admin_api_key
    if expected is None:
        if settings.app_env == "development":
            return
        raise HTTPException(403, "Document management is disabled: ADMIN_API_KEY is not set")
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(401, "Invalid or missing X-API-Key")


@health_router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    # Ready once the models are loaded and the index is connected. Deliberately
    # no live call to Pinecone or Anthropic: an upstream blip would otherwise
    # pull every replica out of the load balancer at once.
    get_pipeline(request)
    return {"status": "ready"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@api_router.post("/chat")
async def chat(
    body: ChatRequest,
    pipeline: RagPipeline = Depends(get_pipeline),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    history = [m.model_dump() for m in body.history[-settings.max_history_messages :]]

    async def events() -> AsyncIterator[str]:
        try:
            chunks = await run_in_threadpool(
                pipeline.retrieve, retrieval_query(body.message, history)
            )
            yield _sse(
                "sources",
                {
                    "sources": [
                        {
                            "index": i,
                            "source": c.source,
                            "page": c.page,
                            "score": round(c.score, 4),
                            "text": c.text,
                        }
                        for i, c in enumerate(chunks, 1)
                    ]
                },
            )
            async for event in pipeline.generate(body.message, history, chunks):
                if isinstance(event, TextDelta):
                    yield _sse("token", {"text": event.text})
                elif isinstance(event, Finished):
                    logger.info(
                        "chat completed model=%s stop_reason=%s input_tokens=%d output_tokens=%d",
                        event.model,
                        event.stop_reason,
                        event.input_tokens,
                        event.output_tokens,
                    )
                    if event.stop_reason == "refusal":
                        yield _sse("error", {"message": "The model declined to answer this."})
                    else:
                        yield _sse("done", {"truncated": event.stop_reason == "max_tokens"})
        except GenerationError as exc:
            yield _sse("error", {"message": str(exc)})
        except Exception:
            logger.exception("chat request failed")
            yield _sse("error", {"message": "Something went wrong. Please try again."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # X-Accel-Buffering stops nginx from holding tokens back.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_router.post("/documents", response_model=IngestResponse, dependencies=[Depends(require_admin)])
async def upload_document(
    file: UploadFile = File(...),
    pipeline: RagPipeline = Depends(get_pipeline),
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds the {settings.max_upload_mb} MB limit")
    try:
        result = await run_in_threadpool(pipeline.ingest, file.filename or "upload", data)
    except DocumentError as exc:
        raise HTTPException(422, str(exc)) from exc
    logger.info("ingested %s as %s (%d chunks)", result.filename, result.doc_id, result.chunks)
    return IngestResponse(doc_id=result.doc_id, filename=result.filename, chunks=result.chunks)


@api_router.delete(
    "/documents/{doc_id}", response_model=DeleteResponse, dependencies=[Depends(require_admin)]
)
async def delete_document(
    doc_id: str, pipeline: RagPipeline = Depends(get_pipeline)
) -> DeleteResponse:
    deleted = await run_in_threadpool(pipeline.delete_document, doc_id)
    return DeleteResponse(doc_id=doc_id, deleted_chunks=deleted)
