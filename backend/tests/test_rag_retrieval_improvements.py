from langchain_core.documents import Document

from app.services.rag_service import rag_service


class _CaptureVectorStore:
    def __init__(self):
        self.docs = []

    def add_documents(self, docs):
        self.docs.extend(docs)


class _FakeVectorStore:
    def __init__(self, scored_docs, document_chunks=None):
        self._scored_docs = scored_docs
        self._document_chunks = document_chunks or {}

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4):
        return self._scored_docs[:k]

    def similarity_search(self, query: str, k: int = 4):
        return [doc for doc, _ in self._scored_docs[:k]]

    def get_document_chunks(self, *, doc_id=None, source=None):
        key = doc_id if doc_id is not None else source
        return self._document_chunks.get(key, [])


def test_ingest_text_adds_page_type_and_section_metadata(monkeypatch):
    capture = _CaptureVectorStore()
    monkeypatch.setattr(rag_service, "get_vector_store", lambda collection_name: capture)

    result = rag_service.ingest_text(
        text=(
            "About Us\n"
            "TangentCloud helps companies modernize operations.\n\n"
            "Services\n"
            "Cloud Migration and Web Development for growth teams."
        ),
        metadata={"source": "https://example.com/about", "title": "About Us"},
        collection_name="tenant-test",
    )

    assert result["status"] == "success"
    assert capture.docs
    assert all((doc.metadata or {}).get("page_type") == "about" for doc in capture.docs)
    assert all("section_key" in (doc.metadata or {}) for doc in capture.docs)
    assert any((doc.metadata or {}).get("section_key") == "about us" for doc in capture.docs)


def test_hybrid_ranking_prefers_about_page_for_identity_queries():
    about_doc = Document(
        page_content="Adamsbridge is a professional services company founded by industry experts.",
        metadata={"source": "https://example.com/about", "title": "About Us", "page_type": "about", "chunk_index": 0},
    )
    blog_doc = Document(
        page_content="Blog post discussing market trends and unrelated commentary.",
        metadata={"source": "https://example.com/blog/post-1", "title": "Blog", "page_type": "low_signal", "chunk_index": 0},
    )

    ranked = rag_service._hybrid_rank_scored_docs(
        "What is Adamsbridge?",
        [
            (blog_doc, 0.91),
            (about_doc, 0.78),
        ],
    )

    assert ranked[0][0].metadata["page_type"] == "about"


def test_retrieve_ranked_docs_expands_adjacent_chunks_for_fact_queries():
    contact_chunk_1 = Document(
        page_content="You can reach our support team at support@example.com for general enquiries.",
        metadata={"doc_id": 10, "source": "https://example.com/contact", "page_type": "contact", "chunk_index": 1, "chunk_count": 3},
    )
    contact_chunk_0 = Document(
        page_content="Contact Us. We respond Monday to Friday.",
        metadata={"doc_id": 10, "source": "https://example.com/contact", "page_type": "contact", "chunk_index": 0, "chunk_count": 3},
    )
    store = _FakeVectorStore(
        scored_docs=[(contact_chunk_1, 0.82)],
        document_chunks={10: [contact_chunk_0, contact_chunk_1]},
    )

    docs = rag_service._retrieve_ranked_docs(store, "What is your contact email?", retrieval_k=3, fetch_k=6)

    chunk_indexes = [int((doc.metadata or {}).get("chunk_index") or 0) for doc in docs]
    assert 1 in chunk_indexes
    assert 0 in chunk_indexes
