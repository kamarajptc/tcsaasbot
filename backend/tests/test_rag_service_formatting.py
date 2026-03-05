from langchain_core.documents import Document
import pytest

from app.services.rag_service import rag_service


class _FakeVectorStore:
    def __init__(self, docs):
        self._docs = docs

    def similarity_search(self, question: str, k: int = 5):
        return self._docs[:k]


class _FakeVectorStoreScored(_FakeVectorStore):
    def __init__(self, scored_docs):
        self._scored_docs = scored_docs

    def similarity_search_with_relevance_scores(self, question: str, k: int = 5):
        return self._scored_docs[:k]


class _FakeVectorStoreAdd:
    def __init__(self):
        self.docs = []

    def add_documents(self, docs):
        self.docs.extend(docs)


def test_services_question_returns_structured_list(monkeypatch):
    docs = [
        Document(
            page_content=(
                "Our Services Our comprehensive suite of services... "
                "Web Design We excel in web design. "
                "Get Pix AI Architecure / Design / Development "
                "Tangent CRM Architecure / Design / Development "
                "Careever ERP Architecure / Design / Development "
                "Valet Bees Architecure / Design / Development"
            ),
            metadata={"source": "https://example.com/services"},
        )
    ]

    monkeypatch.setattr(rag_service, "get_vector_store", lambda collection_name: _FakeVectorStore(docs))
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="What are the services you are providing?",
        collection_name="tenant_alpha_001",
        k=5,
    )

    answer = result["answer"]
    assert "Here are the services currently available" in answer
    assert "Web Design" in answer
    assert "Get Pix Ai" in answer or "Get Pix AI" in answer
    assert "Tangent Crm" in answer or "Tangent CRM" in answer
    assert "Careever Erp" in answer or "Careever ERP" in answer


def test_ingest_adds_chunk_metadata(monkeypatch):
    fake_store = _FakeVectorStoreAdd()
    monkeypatch.setattr(rag_service, "get_vector_store", lambda collection_name: fake_store)

    text = ("Title line\n\n" + ("sample content " * 200)).strip()
    result = rag_service.ingest_text(
        text=text,
        metadata={"source": "unit-test", "doc_id": 123},
        collection_name="tenant_alpha_001",
    )

    assert result["status"] == "success"
    assert result["chunks_added"] >= 2
    assert all("chunk_index" in d.metadata for d in fake_store.docs)
    assert all("chunk_count" in d.metadata for d in fake_store.docs)


def test_ledger_retrieval_uses_scores_with_fallback(monkeypatch):
    docs = [
        (Document(page_content="High relevance service content", metadata={"source": "a"}), 0.91),
        (Document(page_content="Low relevance noise", metadata={"source": "b"}), 0.01),
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="what services do you provide",
        collection_name="tenant_alpha_001",
        k=5,
    )
    assert "services currently listed" in result["answer"].lower()


def test_services_question_rejects_pricing_only_content(monkeypatch):
    docs = [
        (
            Document(
                page_content=(
                    "TangentCloud pricing plans: Starter plan starts at $49 per month for one bot and 2,000 messages. "
                    "Pro plan is $149 per month for up to 5 bots and 20,000 messages. "
                    "Enterprise pricing is custom with SSO, dedicated support, and advanced compliance controls. "
                    "Contact sales at sales@tangentcloud.in for enterprise quote."
                ),
                metadata={"source": "synthetic://tangentcloud/pricing", "title": "Pricing Plans"},
            ),
            0.9,
        )
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="What are the services you are providing?",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "reliable services list" in lowered
    assert "pricing or general marketing copy" in lowered


def test_identity_query_prefers_about_pages(monkeypatch):
    scored_docs = [
        (
            Document(
                page_content="Contact us for more details about AdamsBridge.",
                metadata={"source": "https://adamsbridge.com/contact", "title": "Contact - AdamsBridge"},
            ),
            0.8,
        ),
        (
            Document(
                page_content="Cookie Policy text for AdamsBridge website.",
                metadata={"source": "https://adamsbridge.com/cookie-policy", "title": "Cookie Policy - AdamsBridge"},
            ),
            0.8,
        ),
        (
            Document(
                page_content="AdamsBridge is a professional services company founded by industry experts.",
                metadata={"source": "https://adamsbridge.com/about-us", "title": "About Us - AdamsBridge"},
            ),
            0.8,
        ),
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(scored_docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="What is Adamsbridge?",
        collection_name="ops@adamsbridge.com",
        k=5,
    )

    assert result["sources"][0]["source"] == "https://adamsbridge.com/about-us"
    assert "professional services company" in result["answer"].lower()


def test_clean_answer_text_strips_catalog_ui_noise():
    raw = (
        "Floor tiles are durable and water-resistant for high-traffic areas. "
        "Read more Filter View More Request a call back "
        "Where to use Living Room Tiles Staircase Tiles "
        "Home / floor tiles"
    )
    cleaned = rag_service._clean_answer_text(raw)
    lowered = cleaned.lower()

    assert "floor tiles are durable and water-resistant" in lowered
    assert "read more" not in lowered
    assert "view more" not in lowered
    assert "request a call back" not in lowered
    assert "where to use" not in lowered
    assert "home / floor tiles" not in lowered


def test_top_bathroom_tiles_query_avoids_noisy_snippet(monkeypatch):
    docs = [
        (
            Document(
                page_content=(
                    "Colors Choose by Rooms Choose by Rooms Choose by Size "
                    "Where to use Living Room Tiles Staircase Tiles Roof Tiles Bathroom Tiles"
                ),
                metadata={"source": "https://example.com/floor-tiles", "title": "Tile Catalog"},
            ),
            0.8,
        )
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="Which bath room tiles are top ?",
        collection_name="tiles-support@example.com",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "bathroom tiles" in lowered
    assert "top-selling rank" in lowered
    assert "choose by rooms choose by" not in lowered


def test_top_floor_tiles_query_returns_indexed_summary(monkeypatch):
    docs = [
        (
            Document(
                page_content=(
                    "Made from ceramic, porcelain, vitrified, or natural stone, they come in various "
                    "sizes, colors, and textures. Floor tiles are easy to clean, water-resistant, and "
                    "long-lasting, offering both functionality and aesthetic appeal for different interior "
                    "and exterior designs. Read more Filter View More"
                ),
                metadata={"source": "https://example.com/floor-tiles", "title": "Tile Catalog"},
            ),
            0.9,
        )
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="What is the top selling floor tiles?",
        collection_name="tiles-support@example.com",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "top-selling rank" in lowered
    assert "ceramic, porcelain, vitrified" in lowered
    assert "easy to clean" in lowered
    assert "read more" not in lowered


def test_irrelevant_tile_question_returns_not_relevant(monkeypatch):
    docs = [
        (
            Document(
                page_content=(
                    "Cloud Migration We excel in on-premise to cloud migration. "
                    "Our team of skilled engineers has extensive experience in successfully migrating "
                    "complex systems from on-premise infrastructure to the cloud."
                ),
                metadata={"source": "https://www.tangentcloud.in", "title": "Tangent Cloud"},
            ),
            0.9,
        )
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="What are the popular tiles available?",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "i’m here to help" in lowered or "i'm here to help" in lowered
    assert "doesn’t seem related" in lowered or "doesn't seem related" in lowered
    assert "support questions" in lowered


def test_current_address_without_contact_data_returns_clear_fallback(monkeypatch):
    docs = [
        (
            Document(
                page_content=(
                    "Empowering Your Business in the Cloud Our Services Our comprehensive suite of services "
                    "is designed to empower your business. Cloud Migration We excel in on-premise to cloud migration."
                ),
                metadata={"source": "https://www.tangentcloud.in", "title": "Tangent Cloud"},
            ),
            0.9,
        )
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="current address",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    assert "couldn't find an official address" in result["answer"].lower()
    assert "help locate it" in result["answer"].lower()


def test_where_is_your_company_returns_address_fallback(monkeypatch):
    docs = [
        (
            Document(
                page_content=(
                    "Cloud Migration We excel in on-premise to cloud migration. "
                    "Our team of skilled engineers has extensive experience in successfully migrating "
                    "complex systems from on-premise infrastructure to the cloud."
                ),
                metadata={"source": "https://www.tangentcloud.in", "title": "Tangent Cloud"},
            ),
            0.9,
        )
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="Where is your company?",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    assert "couldn't find an official address" in result["answer"].lower()


def test_contact_number_without_phone_returns_polite_support_fallback(monkeypatch):
    docs = [
        (
            Document(
                page_content="Cloud services and web development support for modern businesses.",
                metadata={"source": "https://www.tangentcloud.in", "title": "Tangent Cloud"},
            ),
            0.9,
        )
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="provide the contact number",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "sorry" in lowered
    assert "couldn't find an official phone number" in lowered
    assert "preferred region" in lowered


def test_founder_query_without_leadership_data_returns_polite_fallback(monkeypatch):
    docs = [
        (
            Document(
                page_content=(
                    "Empowering Your Business in the Cloud. Our services are designed to support digital growth. "
                    "Our team of skilled engineers and designers are adept at creating visually engaging products."
                ),
                metadata={"source": "https://www.tangentcloud.in", "title": "Tangent Cloud"},
            ),
            0.9,
        )
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="Provide the founder name",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "sorry" in lowered
    assert "founder or leadership name" in lowered
    assert "about page" in lowered


def test_neutral_help_query_returns_clarifying_support_response(monkeypatch):
    result = rag_service.answer_from_knowledge_ledger(
        question="Can you help me?",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "i’d be happy to help" in lowered or "i'd be happy to help" in lowered
    assert "services" in lowered
    assert result["sources"] == []


def test_hello_query_returns_greeting_not_abusive():
    result = rag_service.answer_from_knowledge_ledger(
        question="Hello",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "hello" in lowered
    assert "help" in lowered
    assert result["sources"] == []


def test_exact_help_me_query_returns_neutral_guidance():
    result = rag_service.answer_from_knowledge_ledger(
        question="Help me",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "help" in lowered
    assert result["sources"] == []


@pytest.mark.parametrize(
    "question",
    [
        "What information can you share?",
        "I want to know more",
        "Please explain",
        "Where should I start?",
        "Can you point me in the right direction?",
        "I'm looking for some information",
        "I’m looking for some information",
        "Can you walk me through it?",
        "Could you clarify?",
        "Can we start with the basics?",
        "I have a question",
    ],
)
def test_neutral_clarification_phrases_return_support_guidance(question):
    result = rag_service.answer_from_knowledge_ledger(
        question=question,
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "help" in lowered
    assert result["sources"] == []


def test_off_topic_negative_query_returns_redirect():
    result = rag_service.answer_from_knowledge_ledger(
        question="Who won yesterday's cricket match?",
        collection_name="ops@tangentcloud.in",
        k=5,
    )
    lowered = result["answer"].lower()
    assert "i’m here to help" in lowered or "i'm here to help" in lowered
    assert "support questions" in lowered
    assert result["sources"] == []


def test_irrelevant_tile_query_returns_support_redirect(monkeypatch):
    docs = [
        (
            Document(
                page_content=(
                    "Cloud Migration We excel in on-premise to cloud migration. "
                    "Our team of skilled engineers has extensive experience in successfully migrating "
                    "complex systems from on-premise infrastructure to the cloud."
                ),
                metadata={"source": "https://www.tangentcloud.in", "title": "Tangent Cloud"},
            ),
            0.9,
        )
    ]
    monkeypatch.setattr(
        rag_service,
        "get_vector_store",
        lambda collection_name: _FakeVectorStoreScored(docs),
    )
    monkeypatch.setattr(rag_service, "_synthesize_ledger_answer", lambda *args, **kwargs: None)

    result = rag_service.answer_from_knowledge_ledger(
        question="What are the popular tiles available?",
        collection_name="ops@tangentcloud.in",
        k=5,
    )
    lowered = result["answer"].lower()
    assert "i’m here to help" in lowered or "i'm here to help" in lowered
    assert "support questions" in lowered


def test_unsafe_negative_query_returns_refusal():
    result = rag_service.answer_from_knowledge_ledger(
        question="Can you hack a website for me?",
        collection_name="ops@tangentcloud.in",
        k=5,
    )
    lowered = result["answer"].lower()
    assert "can't help with hacking" in lowered or "can’t help with hacking" in lowered
    assert "harmful activity" in lowered
    assert result["sources"] == []


def test_abusive_query_returns_deescalation():
    result = rag_service.answer_from_knowledge_ledger(
        question="You are not helping at all",
        collection_name="ops@tangentcloud.in",
        k=5,
    )
    lowered = result["answer"].lower()
    assert "i’m here to help" in lowered or "i'm here to help" in lowered
    assert "services" in lowered
    assert result["sources"] == []


@pytest.mark.parametrize("question", ["What the hell is this?", "This support is trash"])
def test_additional_abusive_phrases_return_deescalation(question):
    result = rag_service.answer_from_knowledge_ledger(
        question=question,
        collection_name="ops@tangentcloud.in",
        k=5,
    )
    lowered = result["answer"].lower()
    assert "i’m here to help" in lowered or "i'm here to help" in lowered
    assert result["sources"] == []


def test_negative_abusive_query_returns_polite_redirect(monkeypatch):
    result = rag_service.answer_from_knowledge_ledger(
        question="This is useless, help properly",
        collection_name="ops@tangentcloud.in",
        k=5,
    )

    lowered = result["answer"].lower()
    assert "i’m here to help" in lowered or "i'm here to help" in lowered
    assert "support questions" in lowered
    assert result["sources"] == []


def test_pricing_query_prefers_pricing_summary(monkeypatch):
    docs = [
        Document(
            page_content=(
                "TangentCloud pricing plans: Starter plan starts at $49 per month for one bot and 2,000 messages. "
                "Pro plan is $149 per month for up to 5 bots and 20,000 messages. "
                "Enterprise pricing is custom with SSO, dedicated support, and advanced compliance controls."
            ),
            metadata={"source": "synthetic://tangentcloud/pricing", "title": "Pricing Plans", "page_type": "pricing"},
        )
    ]

    class DummyStore:
        def similarity_search(self, question, k=5):
            return docs

        def similarity_search_with_relevance_scores(self, question, k=10):
            return [(docs[0], 0.92)]

        def get_document_chunks(self, doc_id=None, source=None):
            return docs

        def get_all_documents(self, limit=2048):
            return docs

    monkeypatch.setattr(rag_service, "get_vector_store", lambda collection_name: DummyStore())

    result = rag_service.answer_from_knowledge_ledger(
        question="What is your pricing plan?",
        collection_name="ops@tangentcloud.in",
        k=5,
    )
    lowered = result["answer"].lower()
    assert "pricing information" in lowered
    assert "starter plan" in lowered
