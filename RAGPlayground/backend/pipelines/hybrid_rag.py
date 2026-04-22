"""
HybridRAG Pipeline — Vector + BM25 + Reciprocal Rank Fusion + LLM Reranking

Combines semantic search (vector) with keyword search (BM25) for better recall.
"""

import os
import re
import uuid
from typing import Dict, Any, List, Tuple

import chromadb
from rank_bm25 import BM25Okapi

from pipelines.base import BasePipeline
from shared.document_loader import extract_text
from shared.chunking import chunk_text
from shared.ollama_client import ollama_chat, ollama_embed_batch
from config import CHROMA_PATH


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class HybridRAGPipeline(BasePipeline):
    name = "HybridRAG"
    description = "Vector + BM25 + RRF Fusion + LLM Reranking"

    def __init__(self):
        self._client = chromadb.PersistentClient(path=os.path.join(CHROMA_PATH, "hybrid"))
        self._col = self._client.get_or_create_collection(name="hybrid_rag")
        # BM25 state
        self._bm25_docs: List[str] = []
        self._bm25_metas: List[Dict] = []
        self._bm25_index = None
        self._rebuild_bm25()

    def _rebuild_bm25(self):
        """Rebuild BM25 index from ChromaDB."""
        count = self._col.count()
        if count == 0:
            self._bm25_docs, self._bm25_metas, self._bm25_index = [], [], None
            return

        all_docs, all_metas = [], []
        offset = 0
        while True:
            batch = self._col.get(include=["documents", "metadatas"], limit=500, offset=offset)
            docs = batch.get("documents", [])
            metas = batch.get("metadatas", [])
            if not docs:
                break
            all_docs.extend(docs)
            all_metas.extend(metas)
            if len(docs) < 500:
                break
            offset += 500

        self._bm25_docs = all_docs
        self._bm25_metas = all_metas
        corpus = [_tokenize(d) for d in all_docs]
        self._bm25_index = BM25Okapi(corpus) if corpus else None
        print(f"[HybridRAG] BM25 index: {len(all_docs)} chunks")

    def index(self, file_path: str, filename: str, model: str) -> Dict[str, Any]:
        doc_id = str(uuid.uuid4())

        full_text, table_rows = extract_text(file_path, filename)
        if not full_text.strip():
            return {"ok": False, "error": "No text extracted"}

        chunks = chunk_text(full_text, chunk_size=2000, overlap=120)
        chunks = [c for c in chunks if len(c) >= 20]
        if not chunks:
            return {"ok": False, "error": "No chunks after filtering"}

        print(f"[HybridRAG] Embedding {len(chunks)} chunks...")
        embeddings = ollama_embed_batch(chunks)

        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": doc_id, "doc_name": filename, "chunk_index": i} for i in range(len(chunks))]
        self._col.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

        # Rebuild BM25
        self._rebuild_bm25()

        print(f"[HybridRAG] Indexed '{filename}': {len(chunks)} chunks")
        return {
            "ok": True,
            "doc_id": doc_id,
            "doc_name": filename,
            "chunks": len(chunks),
            "details": {"text_length": len(full_text), "table_rows": len(table_rows)},
        }

    def _vector_search(self, question: str, doc_id: str = None, top_k: int = 20) -> List[Tuple[str, Dict]]:
        query_embedding = ollama_embed_batch([question])[0]
        where_filter = {"doc_id": doc_id} if doc_id else None
        results = self._col.query(query_embeddings=[query_embedding], n_results=top_k, where=where_filter)
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        return list(zip(docs, metas))

    def _bm25_search(self, question: str, doc_id: str = None, top_k: int = 20) -> List[Tuple[str, Dict]]:
        if not self._bm25_index:
            return []
        tokens = _tokenize(question)
        if not tokens:
            return []
        scores = self._bm25_index.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        results = []
        for idx in ranked[:top_k * 2]:
            if scores[idx] <= 0:
                break
            meta = self._bm25_metas[idx]
            if doc_id and meta.get("doc_id") != doc_id:
                continue
            results.append((self._bm25_docs[idx], meta))
            if len(results) >= top_k:
                break
        return results

    def _rrf_fuse(self, vector_results: List[Tuple[str, Dict]], bm25_results: List[Tuple[str, Dict]], k: int = 60, top_k: int = 10) -> List[Tuple[str, Dict]]:
        """Reciprocal Rank Fusion."""
        scores = {}
        items = {}

        def _key(text, meta):
            return f"{meta.get('doc_id', '')}_{meta.get('chunk_index', '')}_{text[:80]}"

        for rank, (text, meta) in enumerate(vector_results):
            key = _key(text, meta)
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            items[key] = (text, meta)

        for rank, (text, meta) in enumerate(bm25_results):
            key = _key(text, meta)
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            items[key] = (text, meta)

        ranked = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        return [items[k] for k in ranked[:top_k]]

    def query(self, question: str, model: str, doc_id: str = None) -> Dict[str, Any]:
        if self._col.count() == 0:
            return {"answer": "No documents indexed.", "used_chunks": [], "search_method": "none"}

        # Hybrid search
        vector_results = self._vector_search(question, doc_id, top_k=20)
        bm25_results = self._bm25_search(question, doc_id, top_k=20)
        merged = self._rrf_fuse(vector_results, bm25_results, top_k=10)

        if not merged:
            return {"answer": "No relevant chunks found.", "used_chunks": [], "search_method": "hybrid"}

        # Build context
        context_parts = []
        used_chunks = []
        for doc_text, meta in merged[:5]:
            context_parts.append(f"[{meta.get('doc_name', 'Unknown')} | chunk {meta.get('chunk_index', '?')}]\n{doc_text}")
            used_chunks.append({"doc_name": meta.get("doc_name"), "chunk_index": meta.get("chunk_index"), "text": doc_text[:200]})

        context = "\n\n---\n\n".join(context_parts)

        # LLM answer
        prompt = (
            "Answer the question ONLY from the CONTEXT below. Do NOT use your training knowledge.\n"
            "If the answer is not in the CONTEXT, say 'Not found in the documents.'\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION: {question}\n\n"
            "Answer:"
        )

        answer = ollama_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            model=model,
        )

        return {
            "answer": answer,
            "used_chunks": used_chunks,
            "search_method": "hybrid (vector + BM25 + RRF)",
            "details": {
                "vector_results": len(vector_results),
                "bm25_results": len(bm25_results),
                "merged_results": len(merged),
                "context_length": len(context),
            },
        }

    def list_docs(self) -> List[Dict[str, Any]]:
        if self._col.count() == 0:
            return []

        all_metas = []
        offset = 0
        while True:
            batch = self._col.get(include=["metadatas"], limit=500, offset=offset)
            metas = batch.get("metadatas", [])
            if not metas:
                break
            all_metas.extend(metas)
            if len(metas) < 500:
                break
            offset += 500

        doc_map = {}
        for m in all_metas:
            did = m.get("doc_id", "")
            if did not in doc_map:
                doc_map[did] = {"doc_id": did, "doc_name": m.get("doc_name", ""), "chunks": 0}
            doc_map[did]["chunks"] += 1

        return list(doc_map.values())

    def clear(self) -> Dict[str, Any]:
        count = self._col.count()
        self._client.delete_collection("hybrid_rag")
        self._col = self._client.get_or_create_collection(name="hybrid_rag")
        self._bm25_docs, self._bm25_metas, self._bm25_index = [], [], None
        return {"ok": True, "cleared": count}
