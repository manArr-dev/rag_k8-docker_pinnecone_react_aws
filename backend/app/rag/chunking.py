import re

_SEPARATORS = ("\n\n", "\n", ". ", " ")


def _split(text: str, size: int, separators: tuple[str, ...]) -> list[str]:
    """Break text into pieces of at most `size` chars at the coarsest boundary that works."""
    if len(text) <= size:
        return [text]
    if not separators:
        return [text[i : i + size] for i in range(0, len(text), size)]
    sep, rest = separators[0], separators[1:]
    parts = text.split(sep)
    if len(parts) == 1:
        return _split(text, size, rest)
    pieces: list[str] = []
    for i, part in enumerate(parts):
        piece = part + (sep if i < len(parts) - 1 else "")
        if piece:
            pieces.extend(_split(piece, size, rest))
    return pieces


def split_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    """Split text into chunks of at most `chunk_size` chars, each starting with
    up to `overlap` chars from the end of the previous one."""
    text = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text:
        return []

    # Pieces leave room for the overlap tail, so tail + piece never exceeds chunk_size.
    pieces = _split(text, chunk_size - overlap, _SEPARATORS)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > chunk_size:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            # Start the tail on a word boundary rather than mid-word.
            space = tail.find(" ")
            current = (tail[space + 1 :] if space != -1 else tail) + piece
        else:
            current += piece
    if current.strip():
        chunks.append(current.strip())
    return chunks
