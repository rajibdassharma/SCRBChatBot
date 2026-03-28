import requests
from config import OLLAMA_BASE_URL, PDF_MODEL, EMBED_MODEL, USE_OLLAMA_EMBEDDINGS

# ── sentence-transformers direct GPU (loaded once at startup if enabled) ──────
_st_model = None

def _get_st_model():
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _st_model = SentenceTransformer("mixedbread-ai/mxbai-embed-large-v1", device=device)
        print(f"[Embed] sentence-transformers loaded on {device}")
    return _st_model


def ollama_chat(messages, temperature=0.0, model=None):
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model or PDF_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": 4096}
    }
    r = requests.post(url, json=payload, timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"]

def ollama_embed(text: str, model=None):
    """
    Embed a single text using Ollama or sentence-transformers.
    Returns a single vector (list[float]).
    """
    vecs = ollama_embed_batch([text], model=model)
    return vecs[0]


def ollama_embed_batch(texts: list, model=None, batch_size: int = 64, max_retries: int = 3):
    """
    Embed multiple texts in batches.
    If USE_OLLAMA_EMBEDDINGS=false, uses sentence-transformers (direct GPU, much faster).
    Otherwise, uses Ollama's /api/embed endpoint (HTTP per batch).
    Returns a list of vectors (list[list[float]]).
    """
    if not USE_OLLAMA_EMBEDDINGS:
        return _embed_batch_st(texts, batch_size)

    return _embed_batch_ollama(texts, model, batch_size, max_retries)


def _embed_batch_st(texts: list, batch_size: int = 256):
    """Embed using sentence-transformers directly on GPU."""
    st_model = _get_st_model()
    embeddings = st_model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=True
    )
    return embeddings.tolist()


def _embed_batch_ollama(texts: list, model=None, batch_size: int = 64, max_retries: int = 3):
    """Embed using Ollama HTTP API (original method)."""
    import time

    m = model or EMBED_MODEL
    all_vecs = []
    _dim = None  # will be determined from first successful embedding

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]

        # Try batch /api/embed with retries
        batch_ok = False
        for attempt in range(max_retries):
            try:
                url1 = f"{OLLAMA_BASE_URL}/api/embed"
                payload1 = {"model": m, "input": batch}
                r1 = requests.post(url1, json=payload1, timeout=600)
                if r1.status_code == 200:
                    data = r1.json()
                    if "embeddings" in data and len(data["embeddings"]) == len(batch):
                        all_vecs.extend(data["embeddings"])
                        if _dim is None:
                            _dim = len(data["embeddings"][0])
                        batch_ok = True
                        break
            except Exception as e:
                print(f"[Embed] Batch attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))

        if batch_ok:
            continue

        # Fallback: embed one by one (with retries per chunk)
        print(f"[Embed] Batch failed, falling back to one-by-one for {len(batch)} texts...")
        for text in batch:
            vec = None
            for attempt in range(max_retries):
                try:
                    url2 = f"{OLLAMA_BASE_URL}/api/embeddings"
                    payload2 = {"model": m, "prompt": text}
                    r2 = requests.post(url2, json=payload2, timeout=600)
                    if r2.status_code == 200:
                        vec = r2.json().get("embedding")
                        if vec:
                            if _dim is None:
                                _dim = len(vec)
                            break
                except Exception as e:
                    print(f"[Embed] Single-text attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))

            if vec:
                all_vecs.append(vec)
            else:
                # Use zero-vector placeholder so indexing doesn't break
                dim = _dim or 1024
                print(f"[Embed] Skipping chunk (zero-vector): {text[:80]}...")
                all_vecs.append([0.0] * dim)

    return all_vecs
