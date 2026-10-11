import io
from pathlib import PurePath

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


class DocumentError(ValueError):
    """The uploaded file can't be turned into text; the message is safe to show the caller."""


def load_document(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    """Return the document as (page number, text) pairs. Page is None for non-paginated files."""
    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise DocumentError(f"Unsupported file type '{ext or filename}'. Supported: {supported}")

    if ext == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(i, page.extract_text() or "") for i, page in enumerate(reader.pages, 1)]
        except PyPdfError as exc:
            raise DocumentError(f"Could not read PDF: {exc}") from exc
        return [(n, text) for n, text in pages if text.strip()]

    try:
        return [(None, data.decode("utf-8-sig"))]
    except UnicodeDecodeError as exc:
        raise DocumentError("Text files must be UTF-8 encoded") from exc
