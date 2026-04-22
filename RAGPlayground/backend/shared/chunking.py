"""Text chunking utilities."""

from typing import List


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 120) -> List[str]:
    """Split text into overlapping chunks."""
    text = (text or "").strip()
    if not text:
        return []

    overlap = max(0, min(overlap, chunk_size - 1))
    chunks = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks
