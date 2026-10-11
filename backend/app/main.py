import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .logging_config import configure_logging, request_id_var
from .rag.pipeline import RagPipeline
from .routes import api_router, health_router

logger = logging.getLogger("app")


def create_app(pipeline: RagPipeline | None = None, settings: Settings | None = None) -> FastAPI:
    """Application factory. Run with `uvicorn app.main:create_app --factory`.

    Tests pass a pipeline built from fakes; in production it is built at startup.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if pipeline is not None:
            app.state.pipeline = pipeline
        else:
            from .rag.factory import build_pipeline

            app.state.pipeline = await asyncio.to_thread(build_pipeline, settings)
        logger.info("startup complete")
        yield

    docs = settings.app_env == "development"
    app = FastAPI(
        title="RAG API",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type", "X-API-Key"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        if request.url.path not in ("/healthz", "/readyz"):
            # For streamed responses this is time to first byte, not total duration.
            logger.info(
                "%s %s -> %d in %.0f ms (request_id=%s)",
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - start) * 1000,
                request_id,
            )
        return response

    app.include_router(health_router)
    app.include_router(api_router)
    return app
