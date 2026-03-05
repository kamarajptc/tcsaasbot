"""
Comprehensive API tests for TangentCloud AI Bots Backend.
Tests cover: Dashboard CRUD, Analytics, Leads, Flows, FAQs, Settings, and Health.
"""
import json
import pytest
from bs4 import BeautifulSoup
from app.api.v1 import chat as chat_api
from app.api.v1 import ingest as ingest_api
from app.core.security import create_access_token


def _jwt_headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


TENANT_A = _jwt_headers("tenant_alpha_001")
TENANT_B = _jwt_headers("tenant_beta_002")

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _create_bot(client, name="Test Bot", headers=None, **extra):
    headers = headers or TENANT_A
    payload = {
        "name": name,
        "description": f"Description for {name}",
        "prompt_template": "You are a helpful assistant.",
        "welcome_message": f"Hello from {name}!",
        "primary_color": "#2563eb",
        **extra,
    }
    return client.post("/api/v1/dashboard/", json=payload, headers=headers)


def _create_lead_form(client, bot_id, headers=None):
    headers = headers or TENANT_A
    return client.post("/api/v1/leads/forms", json={
        "bot_id": bot_id,
        "title": "Contact Us",
        "fields": [
            {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
            {"name": "email", "label": "Email", "type": "email", "required": True},
        ]
    }, headers=headers)


def _create_conversation(client, bot_id, headers=None):
    headers = headers or TENANT_A
    resp = client.post(
        "/api/v1/dashboard/conversations",
        json={"bot_id": bot_id},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


# ─────────────────────────────────────────────
# 1. ROOT & HEALTH
# ─────────────────────────────────────────────

class TestHealth:
    def test_root_returns_welcome(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Welcome to" in resp.json()["message"]


# ─────────────────────────────────────────────
# 2. BOT CRUD (Dashboard)
# ─────────────────────────────────────────────

class TestBotCRUD:
    def test_create_bot(self, client):
        resp = _create_bot(client, "Support Sarah")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Support Sarah"
        assert data["tenant_id"] == "tenant_alpha_001"
        assert "id" in data

    def test_create_bot_with_avatar(self, client):
        resp = _create_bot(client, "Avatar Bot", avatar_url="https://example.com/avatar.png")
        assert resp.status_code == 200
        assert resp.json()["avatar_url"] == "https://example.com/avatar.png"

    def test_list_bots_returns_only_own_tenant(self, client):
        _create_bot(client, "Alpha Bot", headers=TENANT_A)
        _create_bot(client, "Beta Bot", headers=TENANT_B)

        resp_a = client.get("/api/v1/dashboard/", headers=TENANT_A)
        resp_b = client.get("/api/v1/dashboard/", headers=TENANT_B)

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        names_a = [b["name"] for b in resp_a.json()]
        names_b = [b["name"] for b in resp_b.json()]
        assert "Alpha Bot" in names_a
        assert "Beta Bot" not in names_a
        assert "Beta Bot" in names_b

    def test_get_bot_by_id(self, client):
        create_resp = _create_bot(client, "Fetch Me")
        bot_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/dashboard/{bot_id}", headers=TENANT_A)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fetch Me"

    def test_get_bot_not_found(self, client):
        resp = client.get("/api/v1/dashboard/9999", headers=TENANT_A)
        assert resp.status_code == 404

    def test_update_bot(self, client):
        create_resp = _create_bot(client, "Old Name")
        bot_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/dashboard/{bot_id}",
            json={"name": "New Name", "primary_color": "#ff0000"},
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        assert resp.json()["primary_color"] == "#ff0000"

    def test_bot_full_config_roundtrip(self, client):
        create_resp = _create_bot(
            client,
            "Config Bot",
            response_mode="knowledge_only",
            placeholder_text="Ask anything",
            bubble_greeting="Need help?",
            tools=["calculator"],
            quick_replies=[{"label": "Pricing", "value": "Show pricing"}],
            canned_responses=[{"id": "1", "title": "Hello", "content": "Hi", "enabled": True}],
            small_talk_responses=[{"trigger": "hi", "response": "hello", "enabled": True}],
            rich_messages_enabled=True,
            greeting_enabled=True,
            greeting_message="Welcome here",
            faq_enabled=True,
            custom_answers={"shipping": "2 days"},
            agent_transfer_enabled=True,
            agent_email="agent@example.com",
            agent_webhook="https://example.com/hook",
            transfer_trigger_keywords=["human", "agent"],
            collect_name=True,
            collect_email=True,
            collect_phone=True,
            collect_custom_fields=[{"name": "company", "required": False}],
            goals=[{"type": "lead"}],
            tags=["sales"],
            ab_test_enabled=True,
            ab_test_variants=[{"name": "A"}],
            enabled_flows=[1, 2],
            flow_data={"nodes": [{"id": "n1"}], "edges": []},
            shopify_enabled=False,
            slack_enabled=False,
            zendesk_enabled=False,
            freshdesk_enabled=False,
        )
        assert create_resp.status_code == 200
        bot_id = create_resp.json()["id"]

        update_resp = client.put(
            f"/api/v1/dashboard/{bot_id}",
            json={
                "description": "Updated bot config",
                "primary_color": "#112233",
                "collect_custom_fields": [{"name": "budget", "required": True}],
                "custom_answers": {"refund": "30 days"},
                "flow_data": {"nodes": [{"id": "n2"}], "edges": []},
            },
            headers=TENANT_A,
        )
        assert update_resp.status_code == 200

        read_resp = client.get(f"/api/v1/dashboard/{bot_id}", headers=TENANT_A)
        assert read_resp.status_code == 200
        data = read_resp.json()
        assert data["response_mode"] == "knowledge_only"
        assert data["placeholder_text"] == "Ask anything"
        assert data["bubble_greeting"] == "Need help?"
        assert data["agent_transfer_enabled"] is True
        assert data["agent_email"] == "agent@example.com"
        assert data["collect_name"] is True
        assert data["collect_email"] is True
        assert data["collect_phone"] is True
        assert data["collect_custom_fields"][0]["name"] == "budget"
        assert data["custom_answers"]["refund"] == "30 days"
        assert data["flow_data"]["nodes"][0]["id"] == "n2"
        assert data["quick_replies"][0]["label"] == "Pricing"
        assert data["enabled_flows"] == [1, 2]

    def test_delete_bot(self, client):
        create_resp = _create_bot(client, "Delete Me")
        bot_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/dashboard/{bot_id}", headers=TENANT_A)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Should be gone now
        resp = client.get(f"/api/v1/dashboard/{bot_id}", headers=TENANT_A)
        assert resp.status_code == 404

    def test_cross_tenant_isolation(self, client):
        """Tenant B should NOT be able to read Tenant A's bot."""
        create_resp = _create_bot(client, "Private Bot", headers=TENANT_A)
        bot_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/dashboard/{bot_id}", headers=TENANT_B)
        assert resp.status_code == 404

    def test_public_bot_access(self, client):
        """Public endpoint should return active bots with safe fields."""
        create_resp = _create_bot(client, "Public Bot", headers=TENANT_A)
        bot_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/dashboard/public/{bot_id}")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["name"] == "Public Bot"
        assert "tenant_id" not in payload
        assert "agent_email" not in payload

    def test_public_bot_access_blocks_inactive_bot(self, client):
        create_resp = _create_bot(client, "Inactive Public Bot", headers=TENANT_A)
        bot_id = create_resp.json()["id"]
        deactivate_resp = client.put(
            f"/api/v1/dashboard/{bot_id}",
            json={"is_active": False},
            headers=TENANT_A,
        )
        assert deactivate_resp.status_code == 200

        resp = client.get(f"/api/v1/dashboard/public/{bot_id}")
        assert resp.status_code == 404


# ─────────────────────────────────────────────
# 3. FAQ CRUD
# ─────────────────────────────────────────────

class TestFAQCRUD:
    def test_create_faq(self, client):
        bot_resp = _create_bot(client, "FAQ Bot")
        bot_id = bot_resp.json()["id"]

        resp = client.post(f"/api/v1/dashboard/{bot_id}/faqs", json={
            "question": "How do I reset my password?",
            "answer": "Go to Settings > Security > Reset."
        }, headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert data["question"] == "How do I reset my password?"
        assert data["bot_id"] == bot_id

    def test_list_faqs(self, client):
        bot_resp = _create_bot(client, "FAQ Bot 2")
        bot_id = bot_resp.json()["id"]

        client.post(f"/api/v1/dashboard/{bot_id}/faqs", json={
            "question": "Q1?", "answer": "A1"
        }, headers=TENANT_A)
        client.post(f"/api/v1/dashboard/{bot_id}/faqs", json={
            "question": "Q2?", "answer": "A2"
        }, headers=TENANT_A)

        resp = client.get(f"/api/v1/dashboard/{bot_id}/faqs", headers=TENANT_A)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_update_faq(self, client):
        bot_resp = _create_bot(client, "FAQ Bot 3")
        bot_id = bot_resp.json()["id"]

        faq_resp = client.post(f"/api/v1/dashboard/{bot_id}/faqs", json={
            "question": "Old Q?", "answer": "Old A"
        }, headers=TENANT_A)
        faq_id = faq_resp.json()["id"]

        resp = client.put(f"/api/v1/dashboard/{bot_id}/faqs/{faq_id}", json={
            "answer": "Updated A"
        }, headers=TENANT_A)
        assert resp.status_code == 200
        assert resp.json()["answer"] == "Updated A"

    def test_delete_faq(self, client):
        bot_resp = _create_bot(client, "FAQ Bot 4")
        bot_id = bot_resp.json()["id"]

        faq_resp = client.post(f"/api/v1/dashboard/{bot_id}/faqs", json={
            "question": "Delete me?", "answer": "Yes"
        }, headers=TENANT_A)
        faq_id = faq_resp.json()["id"]

        resp = client.delete(f"/api/v1/dashboard/{bot_id}/faqs/{faq_id}", headers=TENANT_A)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ─────────────────────────────────────────────
# 4. FLOWS
# ─────────────────────────────────────────────

class TestFlows:
    def test_create_flow(self, client):
        bot_resp = _create_bot(client, "Flow Bot")
        bot_id = bot_resp.json()["id"]

        flow_data = {
            "name": "Lead Capture",
            "description": "Collects email",
            "flow_data": {
                "nodes": [
                    {"id": "n1", "type": "trigger", "data": {"label": "Start"}},
                    {"id": "n2", "type": "message", "data": {"label": "Intro", "message": "Hello!"}},
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            },
        }
        resp = client.post(f"/api/v1/flows/{bot_id}/flows", json=flow_data, headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Lead Capture"
        assert data["version"] == 1

    def test_update_flow_bumps_version(self, client):
        bot_resp = _create_bot(client, "Flow Bot 2")
        bot_id = bot_resp.json()["id"]

        create_resp = client.post(f"/api/v1/flows/{bot_id}/flows", json={
            "name": "V1 Flow",
            "flow_data": {"nodes": [], "edges": []},
        }, headers=TENANT_A)
        flow_id = create_resp.json()["id"]

        resp = client.put(f"/api/v1/flows/{bot_id}/flows/{flow_id}", json={
            "name": "V2 Flow",
            "flow_data": {"nodes": [{"id": "n1"}], "edges": []},
        }, headers=TENANT_A)
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    def test_delete_flow(self, client):
        bot_resp = _create_bot(client, "Flow Bot 3")
        bot_id = bot_resp.json()["id"]

        create_resp = client.post(f"/api/v1/flows/{bot_id}/flows", json={
            "name": "Temp Flow",
            "flow_data": {},
        }, headers=TENANT_A)
        flow_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/flows/{bot_id}/flows/{flow_id}", headers=TENANT_A)
        assert resp.status_code == 200

    def test_cross_tenant_cannot_create_flow(self, client):
        bot_resp = _create_bot(client, "Tenant A Flow Bot", headers=TENANT_A)
        bot_id = bot_resp.json()["id"]

        resp = client.post(
            f"/api/v1/flows/{bot_id}/flows",
            json={"name": "Illegal Flow", "flow_data": {"nodes": [], "edges": []}},
            headers=TENANT_B,
        )
        assert resp.status_code == 404

    def test_runtime_uses_inline_bot_flow_nodes_for_chat(self, client, monkeypatch):
        bot_resp = _create_bot(
            client,
            "Flow Runtime Bot",
            flow_data={
                "nodes": [
                    {
                        "id": "node-kw",
                        "type": "message",
                        "data": {"keywords": ["pricing", "plan"], "message": "Our pricing starts at $19/month."},
                    }
                ],
                "edges": [],
            },
        )
        bot_id = bot_resp.json()["id"]

        async def should_not_run_ai(*args, **kwargs):
            raise AssertionError("AI path should not run when flow runtime matches")

        monkeypatch.setattr(chat_api, "_get_ai_response", should_not_run_ai)

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "Can you share pricing?", "bot_id": bot_id},
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "Our pricing starts at $19/month."

    def test_runtime_uses_enabled_active_saved_flow_nodes(self, client, monkeypatch):
        bot_id = _create_bot(client, "Saved Flow Runtime Bot").json()["id"]
        flow = client.post(
            f"/api/v1/flows/{bot_id}/flows",
            json={
                "name": "Refund Flow",
                "flow_data": {
                    "nodes": [
                        {
                            "id": "saved-1",
                            "type": "message",
                            "data": {"keywords": ["refund"], "message": "Refunds are handled within 30 days."},
                        }
                    ],
                    "edges": [],
                },
                "is_active": True,
            },
            headers=TENANT_A,
        )
        assert flow.status_code == 200
        flow_id = flow.json()["id"]

        upd = client.put(
            f"/api/v1/dashboard/{bot_id}",
            json={"enabled_flows": [flow_id]},
            headers=TENANT_A,
        )
        assert upd.status_code == 200

        async def should_not_run_ai(*args, **kwargs):
            raise AssertionError("AI path should not run when saved flow runtime matches")

        monkeypatch.setattr(chat_api, "_get_ai_response", should_not_run_ai)

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "I want a refund", "bot_id": bot_id},
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "Refunds are handled within 30 days."


class TestTenantIsolationCoverage:
    def test_cross_tenant_chat_to_foreign_bot_returns_404(self, client):
        bot_resp = _create_bot(client, "Tenant A Chat Bot", headers=TENANT_A)
        bot_id = bot_resp.json()["id"]

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "hello", "bot_id": bot_id},
            headers=TENANT_B,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Bot not found"

    def test_cross_tenant_cannot_create_lead_form_for_foreign_bot(self, client):
        bot_resp = _create_bot(client, "Tenant A Lead Bot", headers=TENANT_A)
        bot_id = bot_resp.json()["id"]

        resp = _create_lead_form(client, bot_id, headers=TENANT_B)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Bot not found"

    def test_ingest_document_list_isolated_per_tenant(self, client, monkeypatch):
        monkeypatch.setattr(
            ingest_api.rag_service,
            "ingest_text",
            lambda *args, **kwargs: {"status": "success", "chunks_added": 1},
        )

        ingest_resp = client.post(
            "/api/v1/ingest/",
            json={"text": "Tenant A private doc", "metadata": {"title": "A Doc", "source": "unit-test"}},
            headers=TENANT_A,
        )
        assert ingest_resp.status_code == 200

        a_docs = client.get("/api/v1/ingest/", headers=TENANT_A)
        b_docs = client.get("/api/v1/ingest/", headers=TENANT_B)
        assert a_docs.status_code == 200
        assert b_docs.status_code == 200
        assert len(a_docs.json()) == 1
        assert b_docs.json() == []

    def test_public_history_requires_matching_active_bot(self, client):
        bot_resp = _create_bot(client, "Public History Bot", headers=TENANT_A)
        bot_id = bot_resp.json()["id"]

        chat_resp = client.post(
            "/api/v1/chat/public",
            json={"message": "hello", "bot_id": bot_id},
        )
        assert chat_resp.status_code == 200
        conv_id = chat_resp.json()["conversation_id"]

        wrong_bot = _create_bot(client, "Other Bot", headers=TENANT_A).json()["id"]
        forbidden = client.get(f"/api/v1/chat/public/history?conversation_id={conv_id}&bot_id={wrong_bot}")
        assert forbidden.status_code == 404

        ok = client.get(f"/api/v1/chat/public/history?conversation_id={conv_id}&bot_id={bot_id}")
        assert ok.status_code == 200
        assert len(ok.json()) >= 2


class TestIngestReliability:
    def test_upload_txt_indexes_and_persists(self, client, monkeypatch):
        captured = {"calls": 0, "metadata": None}

        def fake_ingest(text, metadata=None, collection_name="default"):
            captured["calls"] += 1
            captured["metadata"] = metadata or {}
            return {"chunks_added": 1}

        monkeypatch.setattr(ingest_api.rag_service, "ingest_text", fake_ingest)

        resp = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("notes.txt", b"Hello reliability test", "text/plain")},
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "success"
        assert payload["filename"] == "notes.txt"
        assert captured["calls"] == 1
        assert captured["metadata"]["title"] == "notes.txt"
        assert "doc_id" in captured["metadata"]

        listed = client.get("/api/v1/ingest/", headers=TENANT_A)
        assert listed.status_code == 200
        assert any(d["title"] == "notes.txt" and d["source"] == "upload" for d in listed.json())

    def test_upload_invalid_extension_returns_clear_message(self, client):
        resp = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("notes.exe", b"dummy", "application/octet-stream")},
            headers=TENANT_A,
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    def test_upload_pdf_parse_error_returns_clear_message(self, client):
        resp = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("broken.pdf", b"not a real pdf", "application/pdf")},
            headers=TENANT_A,
        )
        assert resp.status_code == 400
        assert "Error parsing PDF" in resp.json()["detail"]

    def test_ingest_rolls_back_sql_when_vector_fails(self, client, monkeypatch):
        def fail_ingest(*args, **kwargs):
            raise Exception("vector store unavailable")

        monkeypatch.setattr(ingest_api.rag_service, "ingest_text", fail_ingest)

        resp = client.post(
            "/api/v1/ingest/",
            json={"text": "rollback body", "metadata": {"title": "Rollback Doc", "source": "unit"}},
            headers=TENANT_A,
        )
        assert resp.status_code == 500
        assert "vector store unavailable" in resp.json()["detail"]

        listed = client.get("/api/v1/ingest/", headers=TENANT_A)
        assert listed.status_code == 200
        assert all(d["title"] != "Rollback Doc" for d in listed.json())

    def test_crawl_audit_summary_endpoint_loads(self, client):
        resp = client.get("/api/v1/ingest/audit/summary", headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_documents" in data
        assert "top_domains" in data

    def test_audit_test_runner_returns_latency_and_pass_fail(self, client, monkeypatch):
        bot_id = _create_bot(client, "Audit Runner Bot").json()["id"]

        def fake_ledger(question, collection_name="default", k=5, bot_instructions="", bot_name=None):
            return {
                "answer": "Refund policy supports returns in 30 days.",
                "sources": [{"source": "https://example.com/refund", "title": "Refund Policy"}],
            }

        monkeypatch.setattr(ingest_api.rag_service, "answer_from_knowledge_ledger", fake_ledger)

        pass_resp = client.post(
            "/api/v1/ingest/audit/test-runner",
            json={"bot_id": bot_id, "question": "What is refund policy?", "expected_keyword": "30 days"},
            headers=TENANT_A,
        )
        assert pass_resp.status_code == 200
        payload = pass_resp.json()
        assert payload["passed"] is True
        assert payload["response_ms"] >= 0
        assert "answer" in payload

        fail_resp = client.post(
            "/api/v1/ingest/audit/test-runner",
            json={"bot_id": bot_id, "question": "What is refund policy?", "expected_keyword": "90 days"},
            headers=TENANT_A,
        )
        assert fail_resp.status_code == 200
        assert fail_resp.json()["passed"] is False


class TestCrawlerDedupeAndSections:
    def test_scrape_dedupes_urls_and_indexes_sections_with_metadata(self, client, monkeypatch):
        captured_meta = []

        def fake_ingest(text, metadata=None, collection_name="default"):
            captured_meta.append(metadata or {})
            return {"chunks_added": 1}

        monkeypatch.setattr(ingest_api.rag_service, "ingest_text", fake_ingest)
        monkeypatch.setattr(ingest_api.rag_service, "delete_document", lambda *args, **kwargs: None)

        class FakeResp:
            def __init__(self, text, status_code=200):
                self.text = text
                self.status_code = status_code
                self.content = text.encode("utf-8")

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise Exception("bad response")

        pages = {
            "https://example.com": """
                <html><head><title>Home</title></head>
                <body>
                  <a href='/about/'>About</a>
                  <section id='faq'><h2>FAQ</h2><p>{}</p></section>
                </body></html>
            """.format("A" * 220),
            "https://example.com/about": """
                <html><head><title>About</title></head>
                <body>
                  <a href='/'>Home</a>
                  <div class='services'><h2>Services</h2><p>{}</p></div>
                </body></html>
            """.format("B" * 230),
        }

        def fake_get(url, headers=None, timeout=None):
            normalized = ingest_api._normalize_url(url)
            if normalized in pages:
                return FakeResp(pages[normalized], 200)
            return FakeResp("<html></html>", 404)

        monkeypatch.setattr(ingest_api.requests, "get", fake_get)

        first = client.post(
            "/api/v1/ingest/scrape",
            json={"url": "https://example.com/", "max_pages": 2, "use_sitemaps": False, "index_sections": True},
            headers=TENANT_A,
        )
        assert first.status_code == 200
        first_data = first.json()
        assert first_data["pages_scraped"] >= 2
        assert first_data["new_pages_indexed"] >= 2
        assert first_data["section_docs_indexed"] >= 2

        second = client.post(
            "/api/v1/ingest/scrape",
            json={"url": "https://example.com", "max_pages": 2, "use_sitemaps": False, "index_sections": True},
            headers=TENANT_A,
        )
        assert second.status_code == 200
        assert second.json()["new_pages_indexed"] == 0

        docs = client.get("/api/v1/ingest/", headers=TENANT_A)
        assert docs.status_code == 200
        sources = [d["source"] for d in docs.json()]
        assert sources.count("https://example.com") == 1
        assert sources.count("https://example.com/about") == 1
        assert any("/__tc_section/" in s for s in sources)
        assert any(m.get("content_type") == "section" and m.get("section_key") for m in captured_meta)

    def test_clean_soup_text_removes_ui_noise_fragments(self):
        html = """
            <html>
              <body>
                <header>Menu Login</header>
                <div>Premium vitrified floor tiles for living room and bedroom applications.</div>
                <div>Request a call back</div>
                <div>View More</div>
                <div>Read more</div>
                <div>Filter</div>
                <div>4 Ft 3 Ft</div>
                <footer>Privacy Policy</footer>
              </body>
            </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        cleaned = ingest_api._clean_soup_text(soup)
        lowered = cleaned.lower()

        assert "premium vitrified floor tiles" in lowered
        assert "request a call back" not in lowered
        assert "view more" not in lowered
        assert "read more" not in lowered
        assert "filter" not in lowered
        assert "privacy policy" not in lowered

    def test_clean_soup_text_dedupes_and_skips_low_signal_lines(self):
        html = """
            <html>
              <body>
                <div>High quality anti-skid floor tiles for wet areas and balconies.</div>
                <div>High quality anti-skid floor tiles for wet areas and balconies.</div>
                <div>abc</div>
                <div>x</div>
                <div>12</div>
              </body>
            </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        cleaned = ingest_api._clean_soup_text(soup).splitlines()

        assert len([line for line in cleaned if "anti-skid floor tiles" in line.lower()]) == 1
        assert all(line.strip().lower() not in {"abc", "x"} for line in cleaned)


# ─────────────────────────────────────────────
# 5. ANALYTICS
# ─────────────────────────────────────────────

class TestAnalytics:
    def test_summary_returns_zeroes_for_new_tenant(self, client):
        resp = client.get("/api/v1/analytics/summary", headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_leads"] == 0
        assert data["total_conversations"] == 0

    def test_trends_returns_seven_days(self, client):
        resp = client.get("/api/v1/analytics/trends", headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 7  # 7-day window

    def test_bot_performance_returns_per_bot(self, client):
        _create_bot(client, "Perf Bot", headers=TENANT_A)
        resp = client.get("/api/v1/analytics/bot-performance", headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["bot_name"] == "Perf Bot"

    def test_ai_performance(self, client):
        resp = client.get("/api/v1/analytics/ai-performance", headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert "resolution_rate" in data
        assert "csat" in data

    def test_summary_metrics_match_fixture_data(self, client):
        bot_id = _create_bot(client, "Analytics Fixture Bot").json()["id"]
        conv_a = _create_conversation(client, bot_id)["id"]
        _create_conversation(client, bot_id)

        lead = client.post("/api/v1/leads/submit", json={
            "bot_id": bot_id,
            "conversation_id": conv_a,
            "data": {"name": "Fixture User", "email": "fx@example.com"},
            "source": "Chat Widget",
        })
        assert lead.status_code == 200

        resp = client.get("/api/v1/analytics/summary", headers=TENANT_A)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total_leads"] == 1
        assert payload["total_conversations"] == 2
        assert payload["conversion_rate"] == 50.0

    def test_trends_include_fixture_day_counts(self, client):
        bot_id = _create_bot(client, "Trend Fixture Bot").json()["id"]
        conv_id = _create_conversation(client, bot_id)["id"]
        lead = client.post("/api/v1/leads/submit", json={
            "bot_id": bot_id,
            "conversation_id": conv_id,
            "data": {"name": "Trend User"},
            "source": "Chat Widget",
        })
        assert lead.status_code == 200

        resp = client.get("/api/v1/analytics/trends", headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 7
        assert any(int(day["conversations"]) >= 1 for day in data)
        assert any(int(day["leads"]) >= 1 for day in data)

    def test_ai_performance_uses_lifecycle_data_not_mock(self, client, db_session):
        from app.core.database import ConversationDB, MessageDB

        bot_id = _create_bot(client, "AI Report Bot").json()["id"]
        conv_ai = _create_conversation(client, bot_id)["id"]
        conv_transfer = _create_conversation(client, bot_id)["id"]
        conv_unresolved = _create_conversation(client, bot_id)["id"]

        c_ai = db_session.query(ConversationDB).filter(ConversationDB.id == conv_ai).first()
        c_transfer = db_session.query(ConversationDB).filter(ConversationDB.id == conv_transfer).first()
        c_unresolved = db_session.query(ConversationDB).filter(ConversationDB.id == conv_unresolved).first()
        c_ai.status = "resolved"
        c_transfer.status = "open"
        c_transfer.agent_requested = True
        c_unresolved.status = "new"
        db_session.add_all([c_ai, c_transfer, c_unresolved])
        db_session.add_all([
            MessageDB(conversation_id=conv_ai, sender="user", text="How do refunds work?"),
            MessageDB(conversation_id=conv_ai, sender="bot", text="Refunds are available in 30 days."),
            MessageDB(conversation_id=conv_transfer, sender="user", text="I need a human now"),
            MessageDB(conversation_id=conv_unresolved, sender="user", text="What are your API limits?"),
        ])
        db_session.commit()

        resp = client.get("/api/v1/analytics/ai-performance", headers=TENANT_A)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total_ai_chats"] == 3
        assert payload["resolution_rate"] == 33.3
        assert payload["transfer_rate"] == 33.3
        assert payload["avg_response_time"].endswith("s")
        assert isinstance(payload["deflection_trend"], list) and len(payload["deflection_trend"]) == 7
        assert len(payload["recent_transfers"]) >= 1
        assert isinstance(payload["top_topics"], list)


# ─────────────────────────────────────────────
# 6. DASHBOARD ANALYTICS SUMMARY
# ─────────────────────────────────────────────

class TestDashboardAnalytics:
    def test_dashboard_analytics_summary(self, client):
        resp = client.get("/api/v1/dashboard/analytics/summary", headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_conversations" in data
        assert "active_bots" in data


# ─────────────────────────────────────────────
# 7. LEADS
# ─────────────────────────────────────────────

class TestLeads:
    def test_create_lead_form(self, client):
        bot_resp = _create_bot(client, "Lead Bot")
        bot_id = bot_resp.json()["id"]

        resp = _create_lead_form(client, bot_id)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Contact Us"
        assert len(data["fields"]) == 2

    def test_get_lead_form_public(self, client):
        bot_resp = _create_bot(client, "Public Lead Bot")
        bot_id = bot_resp.json()["id"]
        _create_lead_form(client, bot_id)

        resp = client.get(f"/api/v1/leads/forms/{bot_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Contact Us"

    def test_get_lead_form_admin_scoped_to_tenant(self, client):
        bot_a = _create_bot(client, "Lead Form A", headers=TENANT_A).json()["id"]
        bot_b = _create_bot(client, "Lead Form B", headers=TENANT_B).json()["id"]
        _create_lead_form(client, bot_a, headers=TENANT_A)
        _create_lead_form(client, bot_b, headers=TENANT_B)

        own = client.get(f"/api/v1/leads/forms/{bot_a}/admin", headers=TENANT_A)
        assert own.status_code == 200
        assert own.json()["bot_id"] == bot_a

        foreign = client.get(f"/api/v1/leads/forms/{bot_a}/admin", headers=TENANT_B)
        assert foreign.status_code == 404

    def test_submit_lead(self, client):
        bot_resp = _create_bot(client, "Submit Bot")
        bot_id = bot_resp.json()["id"]
        conv = _create_conversation(client, bot_id)
        resp = client.post("/api/v1/leads/submit", json={
            "bot_id": bot_id,
            "conversation_id": conv["id"],
            "data": {"full_name": "Elon Musk", "email": "elon@spacex.com"},
            "country": "US",
            "source": "Google Ads"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["bot_id"] == bot_id
        assert data["conversation_id"] == conv["id"]
        assert data["data"]["full_name"] == "Elon Musk"
        assert data["country"] == "US"

    def test_get_leads_list(self, client):
        bot_resp = _create_bot(client, "Leads List Bot")
        bot_id = bot_resp.json()["id"]
        conv = _create_conversation(client, bot_id)

        # Submit two leads
        for name in ["Alice", "Bob"]:
            client.post("/api/v1/leads/submit", json={
                "bot_id": bot_id,
                "conversation_id": conv["id"],
                "data": {"full_name": name, "email": f"{name.lower()}@example.com"},
            })

        resp = client.get("/api/v1/leads/leads", headers=TENANT_A)
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_submit_lead_requires_valid_conversation(self, client):
        bot_id = _create_bot(client, "Lead Validation Bot").json()["id"]
        resp = client.post("/api/v1/leads/submit", json={
            "bot_id": bot_id,
            "conversation_id": 9999,
            "data": {"full_name": "User"},
            "source": "Chat Widget",
        })
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Conversation not found"


# ─────────────────────────────────────────────
# 8. SETTINGS
# ─────────────────────────────────────────────

class TestSettings:
    def test_get_settings_creates_default(self, client):
        resp = client.get("/api/v1/dashboard/settings", headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "starter"
        assert data["id"] == "tenant_alpha_001"

    def test_email_settings_default(self, client):
        resp = client.get("/api/v1/leads/email-settings", headers=TENANT_A)
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_enabled"] is False


# ─────────────────────────────────────────────
# 9. CONVERSATIONS
# ─────────────────────────────────────────────

class TestConversations:
    def test_list_conversations_empty(self, client):
        resp = client.get("/api/v1/dashboard/conversations", headers=TENANT_A)
        assert resp.status_code == 200
        assert resp.json() == []


# ─────────────────────────────────────────────
# 10. CHAT FALLBACKS
# ─────────────────────────────────────────────

class TestChatFallbacks:
    def test_chat_falls_back_to_ledger_when_ai_fails(self, client, monkeypatch):
        bot_resp = _create_bot(client, "Fallback Bot")
        bot_id = bot_resp.json()["id"]

        async def fail_ai(*args, **kwargs):
            raise Exception("provider down")

        def fake_ledger(*args, **kwargs):
            return {
                "answer": "Ledger fallback answer",
                "sources": [{"source": "https://example.com"}],
            }

        monkeypatch.setattr(chat_api, "_get_ai_response", fail_ai)
        monkeypatch.setattr(chat_api.rag_service, "answer_from_knowledge_ledger", fake_ledger)

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "What services?", "bot_id": bot_id},
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"].startswith("Ledger fallback answer")
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source"] == "https://example.com"
        assert "conversation_id" in data

    def test_chat_returns_capacity_message_if_ledger_also_fails(self, client, monkeypatch):
        bot_resp = _create_bot(client, "Fallback Bot 2")
        bot_id = bot_resp.json()["id"]

        async def fail_ai(*args, **kwargs):
            raise Exception("provider down")

        def fail_ledger(*args, **kwargs):
            raise Exception("vector store down")

        monkeypatch.setattr(chat_api, "_get_ai_response", fail_ai)
        monkeypatch.setattr(chat_api.rag_service, "answer_from_knowledge_ledger", fail_ledger)

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "What services?", "bot_id": bot_id},
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "temporarily at capacity" in data["answer"].lower()
        assert data["sources"] == []

    def test_public_chat_falls_back_to_ledger_when_ai_fails(self, client, monkeypatch):
        bot_resp = _create_bot(client, "Public Fallback Bot")
        bot_id = bot_resp.json()["id"]

        async def fail_ai(*args, **kwargs):
            raise Exception("provider down")

        def fake_ledger(*args, **kwargs):
            return {
                "answer": "Public ledger fallback answer",
                "sources": [{"source": "https://example.com/public"}],
            }

        monkeypatch.setattr(chat_api, "_get_ai_response", fail_ai)
        monkeypatch.setattr(chat_api.rag_service, "answer_from_knowledge_ledger", fake_ledger)

        resp = client.post(
            "/api/v1/chat/public",
            json={"message": "What services?", "bot_id": bot_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"].startswith("Public ledger fallback answer")
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source"] == "https://example.com/public"
        assert "conversation_id" in data

    def test_chat_quota_error_path_still_returns_ledger_fallback(self, client, monkeypatch):
        bot_resp = _create_bot(client, "Quota Fallback Bot")
        bot_id = bot_resp.json()["id"]

        async def quota_fail(*args, **kwargs):
            raise Exception("ResourceExhausted: quota exceeded")

        def fake_ledger(*args, **kwargs):
            return {"answer": "Quota-safe fallback answer", "sources": [{"source": "ledger-fallback"}]}

        monkeypatch.setattr(chat_api, "_get_ai_response", quota_fail)
        monkeypatch.setattr(chat_api.rag_service, "answer_from_knowledge_ledger", fake_ledger)

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "Need pricing", "bot_id": bot_id},
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"].startswith("Quota-safe fallback answer")
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source"] == "ledger-fallback"


class TestResponseModes:
    def test_knowledge_only_mode_uses_ledger(self, client, monkeypatch):
        bot_resp = _create_bot(client, "Strict Ledger Bot", response_mode="knowledge_only")
        bot_id = bot_resp.json()["id"]

        def fail_query(*args, **kwargs):
            raise Exception("rag query should not be used in knowledge_only mode")

        def fake_ledger(*args, **kwargs):
            return {"answer": "Strict knowledge answer", "sources": [{"source": "ledger"}]}

        monkeypatch.setattr(chat_api.rag_service, "query", fail_query)
        monkeypatch.setattr(chat_api.rag_service, "answer_from_knowledge_ledger", fake_ledger)

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "What is your api limit?", "bot_id": bot_id},
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"].startswith("Strict knowledge answer")
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source"] == "ledger"

    def test_knowledge_plus_reasoning_mode_uses_rag_query(self, client, monkeypatch):
        bot_resp = _create_bot(client, "Reasoning Bot", response_mode="knowledge_plus_reasoning")
        bot_id = bot_resp.json()["id"]

        def fake_query(*args, **kwargs):
            return {"answer": "Reasoned answer", "sources": [{"source": "rag"}]}

        def fail_ledger(*args, **kwargs):
            raise Exception("ledger fallback should not run in successful rag mode")

        monkeypatch.setattr(chat_api.rag_service, "query", fake_query)
        monkeypatch.setattr(chat_api.rag_service, "answer_from_knowledge_ledger", fail_ledger)

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "What is your api limit?", "bot_id": bot_id},
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"].startswith("Reasoned answer")
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source"] == "rag"
