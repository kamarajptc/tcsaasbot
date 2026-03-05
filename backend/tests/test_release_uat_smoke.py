from app.core.database import TenantDB
from app.core.security import create_access_token


def _headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


def _seed_tenant(db_session, tenant_id: str, plan: str = "enterprise"):
    db_session.add(TenantDB(id=tenant_id, name=f"Tenant {tenant_id}", plan=plan, is_active=True))
    db_session.commit()


class TestReleaseUatSmoke:
    def test_uat_core_bot_knowledge_chat_flow(self, client, db_session, monkeypatch):
        tenant_id = "uat_smoke_core@example.com"
        _seed_tenant(db_session, tenant_id)
        headers = _headers(tenant_id)

        monkeypatch.setattr(
            "app.api.v1.ingest.rag_service.ingest_text",
            lambda text, metadata=None, collection_name="default": {"chunks_added": 1},
        )
        monkeypatch.setattr(
            "app.api.v1.chat.rag_service.query",
            lambda message, collection_name="default", chat_history=None, bot_instructions="", bot_name=None: {
                "answer": "Refunds are allowed within 30 days.",
                "sources": [{"title": "refund policy", "score": 0.98}],
            },
        )

        create_bot = client.post(
            "/api/v1/dashboard/",
            json={
                "name": "UAT Bot",
                "description": "release smoke",
                "prompt_template": "You are helpful.",
                "welcome_message": "Welcome",
                "primary_color": "#2563eb",
            },
            headers=headers,
        )
        assert create_bot.status_code == 200
        bot_id = create_bot.json()["id"]

        ingest = client.post(
            "/api/v1/ingest/",
            json={
                "text": "Our refund policy allows returns within 30 days.",
                "metadata": {"title": "refund policy", "source": "uat"},
            },
            headers=headers,
        )
        assert ingest.status_code == 200

        chat = client.post(
            "/api/v1/chat/",
            json={"bot_id": bot_id, "message": "What is your refund policy?"},
            headers=headers,
        )
        assert chat.status_code == 200
        assert chat.json().get("conversation_id")

        list_docs = client.get("/api/v1/ingest/", headers=headers)
        assert list_docs.status_code == 200
        assert len(list_docs.json()) >= 1

    def test_uat_livechat_leads_integrations_flow(self, client, db_session, monkeypatch):
        tenant_id = "uat_smoke_ops@example.com"
        _seed_tenant(db_session, tenant_id)
        headers = _headers(tenant_id)

        create_bot = client.post(
            "/api/v1/dashboard/",
            json={
                "name": "UAT Ops Bot",
                "description": "release smoke",
                "prompt_template": "You are helpful.",
                "welcome_message": "Welcome",
                "primary_color": "#2563eb",
                "agent_transfer_enabled": True,
            },
            headers=headers,
        )
        assert create_bot.status_code == 200
        bot_id = create_bot.json()["id"]

        save_slack = client.post(
            f"/api/v1/integrations/bots/{bot_id}/integrations",
            json={
                "integration_type": "slack",
                "config": {"webhook_url": "https://hooks.slack.test/services/demo"},
                "is_active": True,
            },
            headers=headers,
        )
        assert save_slack.status_code == 200

        save_shopify = client.post(
            f"/api/v1/integrations/bots/{bot_id}/integrations",
            json={
                "integration_type": "shopify",
                "config": {
                    "store_url": "demo-store.myshopify.com",
                    "access_token": "shpat_test",
                },
                "is_active": True,
            },
            headers=headers,
        )
        assert save_shopify.status_code == 200

        class DummyResponse:
            status_code = 200
            content = b"ok"

            def json(self):
                return {
                    "orders": [
                        {
                            "id": 999,
                            "name": "#A100",
                            "financial_status": "paid",
                            "fulfillment_status": "fulfilled",
                        }
                    ]
                }

        monkeypatch.setattr("app.services.integration_service.requests.get", lambda *args, **kwargs: DummyResponse())

        order_lookup = client.post(
            f"/api/v1/integrations/bots/{bot_id}/shopify/order-lookup",
            json={"order_name": "#A100"},
            headers=headers,
        )
        assert order_lookup.status_code == 200
        assert order_lookup.json()["found"] is True

        conv_resp = client.post(
            "/api/v1/dashboard/conversations",
            json={"bot_id": bot_id},
            headers=headers,
        )
        assert conv_resp.status_code == 200

        lead_submit = client.post(
            "/api/v1/leads/submit",
            json={
                "bot_id": bot_id,
                "conversation_id": conv_resp.json()["id"],
                "data": {"name": "Release User", "email": "release@example.com"},
                "source": "Widget",
            },
        )
        assert lead_submit.status_code == 200

        transfer_rule = client.post(
            f"/api/v1/agent-transfer/bots/{bot_id}/rules",
            json={
                "name": "Escalate",
                "rule_type": "keyword",
                "condition": "human,agent",
                "action": "transfer",
                "transfer_message": "Connecting you to support.",
                "priority": 1,
                "is_active": True,
            },
            headers=headers,
        )
        assert transfer_rule.status_code == 200

        trigger_transfer = client.post(
            "/api/v1/chat/",
            json={"bot_id": bot_id, "message": "Need human support"},
            headers=headers,
        )
        assert trigger_transfer.status_code == 200
        assert "Connecting you to support." in trigger_transfer.json()["answer"]
