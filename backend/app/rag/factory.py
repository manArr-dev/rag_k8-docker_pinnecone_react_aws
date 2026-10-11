import logging

from ..config import Settings
from .pipeline import RagPipeline

logger = logging.getLogger(__name__)


def build_pipeline(settings: Settings) -> RagPipeline:
    """Load the PyTorch models and connect to Pinecone. Slow (seconds); run once at startup."""
    # Imported here so the API layer and its tests don't need torch installed.
    import torch
    from transformers.utils import logging as hf_logging

    from .embeddings import Embedder
    from .generator import ClaudeGenerator
    from .reranker import Reranker
    from .vectorstore import PineconeStore

    if settings.pinecone_api_key is None:
        raise RuntimeError("PINECONE_API_KEY is not set")
    # tqdm bars would otherwise land in the JSON log stream.
    hf_logging.disable_progress_bar()
    if settings.torch_num_threads:
        torch.set_num_threads(settings.torch_num_threads)

    embedder = Embedder(
        settings.embedding_model,
        pooling=settings.embedding_pooling,
        query_prefix=settings.embedding_query_prefix,
        batch_size=settings.embedding_batch_size,
    )
    logger.info(
        "loaded embedding model %s on %s (%d dims)",
        settings.embedding_model,
        embedder.device,
        embedder.dimension,
    )
    reranker = Reranker(settings.reranker_model) if settings.reranker_enabled else None

    store = PineconeStore(
        api_key=settings.pinecone_api_key.get_secret_value(),
        index_name=settings.pinecone_index,
        namespace=settings.pinecone_namespace,
        dimension=embedder.dimension,
        cloud=settings.pinecone_cloud,
        region=settings.pinecone_region,
        create_if_missing=settings.pinecone_create_index,
    )
    generator = ClaudeGenerator(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        effort=settings.llm_effort,
        refusal_fallback=settings.llm_refusal_fallback,
    )
    return RagPipeline(
        embedder=embedder,
        store=store,
        generator=generator,
        reranker=reranker,
        top_k=settings.retrieval_top_k,
        top_n=settings.rerank_top_n,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
