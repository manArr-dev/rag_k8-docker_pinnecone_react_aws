import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class Reranker:
    """Cross-encoder that scores (query, passage) pairs jointly. Slower than the
    bi-encoder used for retrieval but markedly more precise, so it only sees the
    top-k candidates Pinecone returns."""

    def __init__(
        self,
        model_name: str,
        *,
        batch_size: int = 16,
        max_length: int = 512,
        device: str | None = None,
    ) -> None:
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = (
            AutoModelForSequenceClassification.from_pretrained(model_name).to(self.device).eval()
        )
        self._batch_size = batch_size
        self._max_length = max_length

    @torch.inference_mode()
    def score(self, query: str, passages: list[str]) -> list[float]:
        scores: list[float] = []
        for start in range(0, len(passages), self._batch_size):
            chunk = passages[start : start + self._batch_size]
            batch = self._tokenizer(
                [query] * len(chunk),
                chunk,
                padding=True,
                truncation=True,
                max_length=self._max_length,
                return_tensors="pt",
            ).to(self.device)
            scores.extend(self._model(**batch).logits.view(-1).cpu().tolist())
        return scores
