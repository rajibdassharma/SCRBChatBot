import requests
from config import OLLAMA_BASE_URL, DB_MODEL, EMBED_MODEL

def ollama_chat(messages, temperature=0.0, model=None):
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model or DB_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature}
    }
    r = requests.post(url, json=payload, timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"]

def ollama_embed(text: str, model=None):
    """
    Embed text using Ollama.
    Tries /api/embed first, falls back to /api/embeddings for older variants.
    Returns a single vector (list[float]).
    """
    m = model or EMBED_MODEL

    # Preferred endpoint
    url1 = f"{OLLAMA_BASE_URL}/api/embed"
    payload1 = {"model": m, "input": text}
    r1 = requests.post(url1, json=payload1, timeout=600)
    if r1.status_code == 200:
        data = r1.json()
        if "embeddings" in data and data["embeddings"]:
            return data["embeddings"][0]
        if "embedding" in data:
            return data["embedding"]

    # Fallback endpoint
    url2 = f"{OLLAMA_BASE_URL}/api/embeddings"
    payload2 = {"model": m, "prompt": text}
    r2 = requests.post(url2, json=payload2, timeout=600)
    r2.raise_for_status()
    return r2.json()["embedding"]


