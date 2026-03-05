from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Dict, Iterable, List, Sequence

from langchain_core.documents import Document
from qdrant_client import QdrantClient, models


def _normalize_payload(page_content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"page_content": page_content}
    for key, value in (metadata or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[key] = value
        else:
            payload[key] = json.dumps(value, sort_keys=True)
    return payload


def _document_id(collection_name: str, metadata: Dict[str, Any], page_content: str) -> str:
    stable_bits = {
        "collection": collection_name,
        "doc_id": metadata.get("doc_id"),
        "chunk_index": metadata.get("chunk_index"),
        "source": metadata.get("source"),
        "title": metadata.get("title"),
    }
    digest = hashlib.sha1(
        (json.dumps(stable_bits, sort_keys=True, default=str) + page_content).encode("utf-8")
    ).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection_name}:{digest}"))


class QdrantCollectionStore:
    def __init__(self, client: QdrantClient, collection_name: str, embeddings):
        self.client = client
        self.collection_name = collection_name
        self.embeddings = embeddings

    def _ensure_collection(self, vector_size: int) -> None:
        if self.client.collection_exists(self.collection_name):
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )

    def add_documents(self, docs: Sequence[Document]) -> None:
        if not docs:
            return
        texts = [doc.page_content for doc in docs]
        vectors = self.embeddings.embed_documents(texts)
        if not vectors:
            return
        self._ensure_collection(len(vectors[0]))
        points: List[models.PointStruct] = []
        for doc, vector in zip(docs, vectors):
            metadata = dict(doc.metadata or {})
            payload = _normalize_payload(doc.page_content, metadata)
            points.append(
                models.PointStruct(
                    id=_document_id(self.collection_name, metadata, doc.page_content),
                    vector=vector,
                    payload=payload,
                )
            )
        self.client.upsert(collection_name=self.collection_name, points=points, wait=True)

    def _to_document(self, payload: Dict[str, Any] | None) -> Document:
        payload = dict(payload or {})
        page_content = str(payload.pop("page_content", ""))
        return Document(page_content=page_content, metadata=payload)

    def similarity_search(self, query: str, k: int = 4) -> List[Document]:
        query_vector = self.embeddings.embed_query(query)
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=k,
            with_payload=True,
        )
        return [self._to_document(point.payload) for point in response.points]

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4):
        query_vector = self.embeddings.embed_query(query)
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=k,
            with_payload=True,
        )
        return [
            (self._to_document(point.payload), float(point.score if point.score is not None else 0.0))
            for point in response.points
        ]

    def get_document_chunks(self, *, doc_id: int | None = None, source: str | None = None) -> List[Document]:
        if doc_id is None and not source:
            return []

        must: List[models.FieldCondition] = []
        if doc_id is not None:
            must.append(
                models.FieldCondition(
                    key="doc_id",
                    match=models.MatchValue(value=doc_id),
                )
            )
        elif source:
            must.append(
                models.FieldCondition(
                    key="source",
                    match=models.MatchValue(value=source),
                )
            )

        records, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(must=must),
            limit=512,
            with_payload=True,
            with_vectors=False,
        )
        docs = [self._to_document(point.payload) for point in records]
        return sorted(docs, key=lambda doc: int((doc.metadata or {}).get("chunk_index") or 0))

    def get_all_documents(self, limit: int = 2048) -> List[Document]:
        records, _ = self.client.scroll(
            collection_name=self.collection_name,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [self._to_document(point.payload) for point in records]

    def delete_by_doc_id(self, doc_id: int) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id),
                    )
                ]
            ),
            wait=True,
        )

    def count(self) -> int:
        records, _ = self.client.scroll(
            collection_name=self.collection_name,
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        if hasattr(self.client, "count"):
            try:
                count_response = self.client.count(self.collection_name, exact=True)
                return int(count_response.count)
            except Exception:
                pass
        return len(records)
