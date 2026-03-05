from app.api.v1 import chat as chat_api
from app.api.v1 import ingest as ingest_api
from app.core.security import create_access_token


def _headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


TENANT_A = _headers("reg_a@example.com")
TENANT_B = _headers("reg_b@example.com")


def _create_bot(client, name: str, headers):
    resp = client.post(
        "/api/v1/dashboard/",
        json={
            "name": name,
            "description": "regression bot",
            "prompt_template": "You are helpful",
            "welcome_message": "Hi",
            "primary_color": "#2563eb",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()["id"]


class TestChatIngestRegression:
    def test_upload_crawl_chat_fallback_and_tenant_isolation(self, client, monkeypatch):
        monkeypatch.setattr(ingest_api.rag_service, "ingest_text", lambda *args, **kwargs: {"chunks_added": 1})

        # Upload path should succeed for tenant A and stay isolated from tenant B.
        up = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("kb.txt", b"Knowledge body", "text/plain")},
            headers=TENANT_A,
        )
        assert up.status_code == 200

        docs_a = client.get("/api/v1/ingest/", headers=TENANT_A)
        docs_b = client.get("/api/v1/ingest/", headers=TENANT_B)
        assert docs_a.status_code == 200 and len(docs_a.json()) >= 1
        assert docs_b.status_code == 200 and docs_b.json() == []

        # Crawl path should succeed with normalized dedupe behavior.
        class FakeResp:
            def __init__(self, text):
                self.text = text
                self.status_code = 200
                self.content = text.encode("utf-8")

            def raise_for_status(self):
                return None

        html = "<html><head><title>Root</title></head><body><a href='/about/'>About</a><section id='faq'><p>{}</p></section></body></html>".format("A" * 220)
        html_about = "<html><head><title>About</title></head><body><a href='/'>Home</a></body></html>"

        def fake_get(url, headers=None, timeout=None):
            normalized = ingest_api._normalize_url(url)
            if normalized == "https://example.com":
                return FakeResp(html)
            return FakeResp(html_about)

        monkeypatch.setattr(ingest_api.requests, "get", fake_get)
        monkeypatch.setattr(ingest_api.rag_service, "delete_document", lambda *args, **kwargs: None)

        scrape_1 = client.post(
            "/api/v1/ingest/scrape",
            json={"url": "https://example.com/", "max_pages": 2, "use_sitemaps": False, "index_sections": True},
            headers=TENANT_A,
        )
        assert scrape_1.status_code == 200

        scrape_2 = client.post(
            "/api/v1/ingest/scrape",
            json={"url": "https://example.com", "max_pages": 2, "use_sitemaps": False, "index_sections": True},
            headers=TENANT_A,
        )
        assert scrape_2.status_code == 200
        assert scrape_2.json()["new_pages_indexed"] == 0

        # Chat fallback path when AI provider fails.
        bot_id = _create_bot(client, "Regression Chat Bot", TENANT_A)

        async def fail_ai(*args, **kwargs):
            raise Exception("provider failure")

        monkeypatch.setattr(chat_api, "_get_ai_response", fail_ai)
        monkeypatch.setattr(
            chat_api.rag_service,
            "answer_from_knowledge_ledger",
            lambda *args, **kwargs: {"answer": "Fallback answer", "sources": [{"source": "ledger"}]},
        )

        chat_resp = client.post(
            "/api/v1/chat/",
            json={"bot_id": bot_id, "message": "Need fallback"},
            headers=TENANT_A,
        )
        assert chat_resp.status_code == 200
        assert chat_resp.json()["answer"] == "Fallback answer."
        assert chat_resp.json()["sources"][0]["source"] == "ledger"

        # Tenant B cannot chat against tenant A bot.
        forbidden = client.post(
            "/api/v1/chat/",
            json={"bot_id": bot_id, "message": "cross tenant"},
            headers=TENANT_B,
        )
        assert forbidden.status_code == 404
