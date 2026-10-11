import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer


class Embedder:
    """Dense text encoder: a Hugging Face transformer run directly in PyTorch."""

    def __init__(
        self,
        model_name: str,
        *,
        pooling: str = "cls",
        query_prefix: str = "",
        batch_size: int = 32,
        max_length: int = 512,
        device: str | None = None,
    ) -> None:
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModel.from_pretrained(model_name).to(self.device).eval()
        self._pooling = pooling
        self._query_prefix = query_prefix
        self._batch_size = batch_size
        self._max_length = max_length

    @property
    def dimension(self) -> int:
        return int(self._model.config.hidden_size)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self._query_prefix + text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    @torch.inference_mode()
    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors: list[torch.Tensor] = []
        for start in range(0, len(texts), self._batch_size):
            batch = self._tokenizer(
                texts[start : start + self._batch_size],
                padding=True,
                truncation=True,
                max_length=self._max_length,
                return_tensors="pt",
            ).to(self.device)
            hidden = self._model(**batch).last_hidden_state
            if self._pooling == "cls":
                pooled = hidden[:, 0]
            else:
                mask = batch["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            # Unit-length vectors, so cosine similarity in Pinecone equals dot product.
            vectors.append(F.normalize(pooled, p=2, dim=-1).cpu())
        return torch.cat(vectors).tolist() if vectors else []
