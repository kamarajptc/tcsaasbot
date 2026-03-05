
import pytest
from app.services.rag_service import rag_service
from unittest.mock import MagicMock, patch

# Mock embeddings to avoid API calls during tests
class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[0.1] * 1536 for _ in texts]
    def embed_query(self, text):
        return [0.1] * 1536

@pytest.fixture
def mock_rag_deps():
    # Inject fake embeddings directly into the already initialized singleton
    original_embeddings = rag_service.embeddings
    rag_service.embeddings = FakeEmbeddings()
    
    with patch("app.services.rag_service._get_llm") as mock_llm:
        # Mock LLM to return a simple response
        mock_response = MagicMock()
        # Mock the __call__ or invoke based on how langchain uses it
        mock_response.invoke.return_value = MagicMock(answer="This is a test answer", context=[])
        mock_llm.return_value = mock_response
        yield
        
    # Restore original (optional but good practice)
    rag_service.embeddings = original_embeddings

class TestSaaSRAGIsolation:
    def test_rag_isolation_between_tenants(self, mock_rag_deps):
        """
        Verify that documents ingested by tenant_A are NOT accessible by tenant_B.
        """
        tenant_a = "tenant_alpha"
        tenant_b = "tenant_beta"
        
        # 1. Ingest content for Tenant A
        rag_service.ingest_text(
            text="The secret password for Alpha is 'BANANA'.",
            metadata={"source": "alpha_docs", "doc_id": 1},
            collection_name=tenant_a
        )
        
        # 2. Ingest DIFFERENT content for Tenant B
        rag_service.ingest_text(
            text="The secret password for Beta is 'CHERRY'.",
            metadata={"source": "beta_docs", "doc_id": 2},
            collection_name=tenant_b
        )
        
        # 3. Verify the isolated vector collections directly.
        
        # Let's check that we have separate collections in the vector store
        store_a = rag_service.get_vector_store(tenant_a)
        store_b = rag_service.get_vector_store(tenant_b)
        
        # Querying store A should find Alpha's content
        results_a = store_a.similarity_search("password", k=1)
        assert len(results_a) > 0
        assert "BANANA" in results_a[0].page_content
        assert "CHERRY" not in results_a[0].page_content
        
        # Querying store B should find Beta's content
        results_b = store_b.similarity_search("password", k=1)
        assert len(results_b) > 0
        assert "CHERRY" in results_b[0].page_content
        assert "BANANA" not in results_b[0].page_content

    def test_rag_sanitization_is_safe(self, mock_rag_deps):
        """
        Verify that special characters in tenant IDs don't break collection naming.
        """
        messy_tenant = "user@domain.com!#$"
        rag_service.ingest_text(
            text="Messy tenant content",
            metadata={"doc_id": 99},
            collection_name=messy_tenant
        )
        
        # If it didn't raise, it's good. Let's verify we can retrieve.
        store = rag_service.get_vector_store(messy_tenant)
        results = store.similarity_search("content")
        assert len(results) > 0
        assert "Messy tenant content" in results[0].page_content
