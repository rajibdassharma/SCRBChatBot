"""
BasicRAG Pipeline — Chunk → Embed → Vector Search → LLM Answer

The simplest RAG approach. Good baseline for comparison.
"""

import os
import uuid
from typing import Dict, Any, List

import chromadb

from pipelines.base import BasePipeline
from shared.document_loader import extract_text
from shared.chunking import chunk_text
from shared.ollama_client import ollama_chat, ollama_embed_batch
from config import CHROMA_PATH


class BasicRAGPipeline(BasePipeline):
    name = "BasicRAG"
    description = "Chunk → Embed → Vector Search → LLM Answer"

    def __init__(self):
        self._client = chromadb.PersistentClient(path=os.path.join(CHROMA_PATH, "basic"))
        self._col = self._client.get_or_create_collection(name="basic_rag")

    def index(self, file_path: str, filename: str, model: str) -> Dict[str, Any]:
        doc_id = str(uuid.uuid4())

        # Extract text
        full_text, table_rows = extract_text(file_path, filename)
        if not full_text.strip():
            return {"ok": False, "error": "No text extracted"}

        # Chunk
        chunks = chunk_text(full_text, chunk_size=2000, overlap=120)
        chunks = [c for c in chunks if len(c) >= 20]
        if not chunks:
            return {"ok": False, "error": "No chunks after filtering"}

        # Embed
        print(f"[BasicRAG] Embedding {len(chunks)} chunks...")
        embeddings = ollama_embed_batch(chunks)

        # Store
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": doc_id, "doc_name": filename, "chunk_index": i} for i in range(len(chunks))]
        self._col.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

        print(f"[BasicRAG] Indexed '{filename}': {len(chunks)} chunks")
        return {
            "ok": True,
            "doc_id": doc_id,
            "doc_name": filename,
            "chunks": len(chunks),
            "details": {"text_length": len(full_text), "table_rows": len(table_rows)},
        }

    def query(self, question: str, model: str, doc_id: str = None) -> Dict[str, Any]:
        if self._col.count() == 0:
            return {"answer": "No documents indexed.", "used_chunks": [], "search_method": "none"}

        # Vector search
        query_embedding = ollama_embed_batch([question])[0]
        where_filter = {"doc_id": doc_id} if doc_id else None
        results = self._col.query(
            query_embeddings=[query_embedding],
            n_results=5,
            where=where_filter,
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not docs:
            return {"answer": "No relevant chunks found.", "used_chunks": [], "search_method": "vector"}

        # Build context
        context_parts = []
        used_chunks = []
        for doc_text, meta in zip(docs, metas):
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
            "search_method": "vector",
            "details": {"context_length": len(context), "chunks_used": len(docs)},
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

        # Group by doc_id
        doc_map = {}
        for m in all_metas:
            did = m.get("doc_id", "")
            if did not in doc_map:
                doc_map[did] = {"doc_id": did, "doc_name": m.get("doc_name", ""), "chunks": 0}
            doc_map[did]["chunks"] += 1

        return list(doc_map.values())

    def clear(self) -> Dict[str, Any]:
        count = self._col.count()
        self._client.delete_collection("basic_rag")
        self._col = self._client.get_or_create_collection(name="basic_rag")
        return {"ok": True, "cleared": count}
