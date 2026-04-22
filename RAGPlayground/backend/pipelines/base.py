"""Base pipeline interface — all RAG pipelines implement this."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List


class BasePipeline(ABC):
    """Abstract base for all RAG pipelines."""

    name: str = "base"
    description: str = "Base pipeline"

    @abstractmethod
    def index(self, file_path: str, filename: str, model: str) -> Dict[str, Any]:
        """
        Index a document.
        Returns: {ok, doc_id, doc_name, chunks, details}
        """
        ...

    @abstractmethod
    def query(self, question: str, model: str, doc_id: str = None) -> Dict[str, Any]:
        """
        Answer a question.
        Returns: {answer, used_chunks, search_method, details}
        """
        ...

    @abstractmethod
    def list_docs(self) -> List[Dict[str, Any]]:
        """
        List indexed documents.
        Returns: [{doc_id, doc_name, chunks}]
        """
        ...

    @abstractmethod
    def clear(self) -> Dict[str, Any]:
        """
        Clear all indexed data.
        Returns: {ok, cleared}
        """
        ...
