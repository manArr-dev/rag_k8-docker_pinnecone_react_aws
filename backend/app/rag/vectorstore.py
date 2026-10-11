import logging

from pinecone import Pinecone, ServerlessSpec
from pinecone.exceptions import NotFoundException

from .types import RetrievedChunk, VectorRecord

logger = logging.getLogger(__name__)

_UPSERT_BATCH = 100
_DELETE_BATCH = 1000


class PineconeStore:
    def __init__(
        self,
        *,
        api_key: 'pcsk_6iS9TY_PxHL19LNEdQNHd7npVYZuiMmkdnhZ1Zb59UwxKf7ZMQQZ9wYGYNj31DjtEt6Rpt',
        index_name: 'prodrag',
        namespace: 'production',
        dimension: 1024,
        cloud: 'aws',
        region: 'us-east-1',
        create_if_missing: bool,
    ) -> None:
        pc = Pinecone(api_key=api_key)
        if not pc.has_index(index_name):
            if not create_if_missing:
                raise RuntimeError(f"Pinecone index '{index_name}' does not exist")
            logger.info("creating Pinecone index %s (%d dims)", index_name, dimension)
            try:
                pc.create_index(
                    name=index_name,
                    dimension=dimension,
                    metric="cosine",
                    spec=ServerlessSpec(cloud=cloud, region=region),
                )
            except Exception:
                # Another replica starting at the same moment may have created it.
                if not pc.has_index(index_name):
                    raise

        description = pc.describe_index(index_name)
        if description.dimension != dimension:
            raise RuntimeError(
                f"Pinecone index '{index_name}' has dimension {description.dimension} but the "
                f"embedding model produces {dimension}. Use a different index or model."
            )
        self._index = pc.Index(host=description.host)
        self._namespace = namespace

    def upsert(self, records: list[VectorRecord]) -> None:
        for start in range(0, len(records), _UPSERT_BATCH):
            self._index.upsert(
                vectors=[
                    {"id": r.id, "values": r.values, "metadata": r.metadata}
                    for r in records[start : start + _UPSERT_BATCH]
                ],
                namespace=self._namespace,
            )

    def query(self, vector: list[float], top_k: int) -> list[RetrievedChunk]:
        result = self._index.query(
            vector=vector, top_k=top_k, include_metadata=True, namespace=self._namespace
        )
        chunks = []
        for match in result.matches:
            meta = match.metadata or {}
            page = meta.get("page")
            chunks.append(
                RetrievedChunk(
                    id=match.id,
                    text=str(meta.get("text", "")),
                    source=str(meta.get("source", "unknown")),
                    page=int(page) if page is not None else None,
                    score=float(match.score),
                )
            )
        return chunks

    def delete_document(self, doc_id: str) -> int:
        """Delete every chunk of a document. Chunk ids are '<doc_id>#<n>', so a
        prefix listing finds them without a metadata filter."""
        deleted = 0
        try:
            for ids in self._index.list(prefix=f"{doc_id}#", namespace=self._namespace):
                ids = list(ids)
                for start in range(0, len(ids), _DELETE_BATCH):
                    batch = ids[start : start + _DELETE_BATCH]
                    self._index.delete(ids=batch, namespace=self._namespace)
                    deleted += len(batch)
        except NotFoundException:
            # The namespace doesn't exist until the first upsert.
            return 0
        return deleted
