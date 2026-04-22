"""Ollama LLM and embedding client."""

import requests
from config import OLLAMA_BASE_URL, DEFAULT_MODEL, EMBED_MODEL


def ollama_chat(messages, temperature=0.0, model=None, max_tokens=4096):
    """Call Ollama chat API. Returns response text."""
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    r = requests.post(url, json=payload, timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"]


def _sanitize_text(text):
    """Clean text for embedding — Ollama rejects empty or whitespace-only input."""
    if not text or not isinstance(text, str):
        return None
    cleaned = text.strip()
    if not cleaned or len(cleaned) < 3:
        return None
    return cleaned


def ollama_embed_batch(texts, model=None, batch_size=64):
    """Embed a list of texts. Returns list of vectors."""
    model = model or EMBED_MODEL
    all_vectors = []

    for i in range(0, len(texts), batch_size):
        batch_raw = texts[i:i + batch_size]
        # Sanitize: replace empty/short texts with placeholder to keep alignment
        batch = []
        skip_indices = set()
        for j, t in enumerate(batch_raw):
            cleaned = _sanitize_text(t)
            if cleaned:
                batch.append(cleaned)
            else:
                skip_indices.add(j)

        # Add zero vectors for skipped texts
        if not batch:
            all_vectors.extend([[0.0]] * len(batch_raw))
            continue

        try:
            r = requests.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": model, "input": batch},
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            vectors = data.get("embeddings", [])
            # Re-insert zero vectors at skipped positions
            vec_iter = iter(vectors)
            for j in range(len(batch_raw)):
                if j in skip_indices:
                    all_vectors.append([0.0])
                else:
                    all_vectors.append(next(vec_iter, [0.0]))
        except Exception as e:
            print(f"[Embed] Batch {i//batch_size + 1} failed: {e}")
            # Fallback: embed one by one
            for text in batch_raw:
                cleaned = _sanitize_text(text)
                if not cleaned:
                    all_vectors.append([0.0])
                    continue
                try:
                    r = requests.post(
                        f"{OLLAMA_BASE_URL}/api/embed",
                        json={"model": model, "input": [cleaned]},
                        timeout=60,
                    )
                    r.raise_for_status()
                    vecs = r.json().get("embeddings", [])
                    all_vectors.extend(vecs if vecs else [[0.0]])
                except Exception as e2:
                    print(f"[Embed] Single text failed ({len(cleaned)} chars): {e2}")
                    all_vectors.append([0.0])

    return all_vectors


def ollama_embed(text, model=None):
    """Embed a single text. Returns one vector."""
    vecs = ollama_embed_batch([text], model=model)
    return vecs[0] if vecs else [0.0]


def list_models():
    """List installed Ollama models."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []
