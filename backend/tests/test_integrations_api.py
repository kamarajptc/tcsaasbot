from app.core.database import TenantDB
from app.core.security import create_access_token
from app.services.integration_service import integration_service


def _jwt_headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


def _seed_tenant(db_session, tenant_id: str):
    tenant = TenantDB(id=tenant_id, name=f"Tenant {tenant_id}", plan="starter", is_active=True)
    db_session.add(tenant)
    db_session.commit()


def _create_bot(client, headers, name="Integration Bot"):
    resp = client.post(
        "/api/v1/dashboard/",
        json={
            "name": name,
            "description": "integration test bot",
            "prompt_template": "You are helpful.",
            "welcome_message": "Hi",
            "primary_color": "#2563eb",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


class TestIntegrationsApi:
    def test_upsert_and_list_integration(self, client, db_session):
        tenant_id = "integrations@example.com"
        headers = _jwt_headers(tenant_id)
        _seed_tenant(db_session, tenant_id)
        bot = _create_bot(client, headers)

        upsert = client.post(
            f"/api/v1/integrations/bots/{bot['id']}/integrations",
            json={
                "integration_type": "shopify",
                "config": {"storeUrl": "example.myshopify.com"},
                "is_active": True,
            },
            headers=headers,
        )
        assert upsert.status_code == 200
        assert upsert.json()["integration_type"] == "shopify"

        listed = client.get(f"/api/v1/integrations/bots/{bot['id']}/integrations", headers=headers)
        assert listed.status_code == 200
        rows = listed.json()
        assert len(rows) == 1
        assert rows[0]["config"]["storeUrl"] == "example.myshopify.com"

    def test_cross_tenant_bot_integration_access_denied(self, client, db_session):
        tenant_a = "integrations_a@example.com"
        tenant_b = "integrations_b@example.com"
        headers_a = _jwt_headers(tenant_a)
        headers_b = _jwt_headers(tenant_b)
        _seed_tenant(db_session, tenant_a)
        _seed_tenant(db_session, tenant_b)
        bot = _create_bot(client, headers_a, name="A Bot")

        forbidden = client.get(f"/api/v1/integrations/bots/{bot['id']}/integrations", headers=headers_b)
        assert forbidden.status_code == 404

    def test_delete_integration(self, client, db_session):
        tenant_id = "integrations_delete@example.com"
        headers = _jwt_headers(tenant_id)
        _seed_tenant(db_session, tenant_id)
        bot = _create_bot(client, headers)

        client.post(
            f"/api/v1/integrations/bots/{bot['id']}/integrations",
            json={"integration_type": "slack", "config": {"channel": "#sales"}, "is_active": True},
            headers=headers,
        )
        deleted = client.delete(f"/api/v1/integrations/bots/{bot['id']}/integrations/slack", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json()["ok"] is True

    def test_shopify_order_lookup_action(self, client, db_session, monkeypatch):
        tenant_id = "integrations_shopify@example.com"
        headers = _jwt_headers(tenant_id)
        _seed_tenant(db_session, tenant_id)
        bot = _create_bot(client, headers, name="Shopify Bot")

        upsert = client.post(
            f"/api/v1/integrations/bots/{bot['id']}/integrations",
            json={
                "integration_type": "shopify",
                "config": {
                    "store_url": "demo-store.myshopify.com",
                    "access_token": "shpat_test",
                    "api_version": "2024-10",
                },
                "is_active": True,
            },
            headers=headers,
        )
        assert upsert.status_code == 200

        class DummyResponse:
            status_code = 200
            content = b"ok"

            def json(self):
                return {
                    "orders": [
                        {
                            "id": 12345,
                            "name": "#1001",
                            "financial_status": "paid",
                            "fulfillment_status": "fulfilled",
                            "cancelled_at": None,
                            "created_at": "2026-02-20T10:00:00Z",
                            "total_price": "49.99",
                            "currency": "USD",
                            "email": "buyer@example.com",
                        }
                    ]
                }

        captured = {}

        async def fake_lookup_shopify_order_async(db, tenant_id, bot_id, order_name, email=None):
            captured["url"] = url
            captured["headers"] = {
                "X-Shopify-Access-Token": "shpat_test",
                "Content-Type": "application/json",
            }
            captured["params"] = {"name": order_name, "email": email}
            captured["timeout"] = 8
            return {
                "found": True,
                "order": DummyResponse().json()["orders"][0],
            }

        url = "https://demo-store.myshopify.com/admin/api/2024-10/orders.json"
        monkeypatch.setattr(integration_service, "lookup_shopify_order_async", fake_lookup_shopify_order_async)

        resp = client.post(
            f"/api/v1/integrations/bots/{bot['id']}/shopify/order-lookup",
            json={"order_name": "#1001", "email": "buyer@example.com"},
            headers=headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["found"] is True
        assert payload["order"]["name"] == "#1001"
        assert payload["order"]["financial_status"] == "paid"
        assert captured["url"].startswith("https://demo-store.myshopify.com/admin/api/2024-10/orders.json")
        assert captured["params"]["name"] == "#1001"
        assert captured["params"]["email"] == "buyer@example.com"
        assert captured["headers"]["X-Shopify-Access-Token"] == "shpat_test"

    def test_lead_submit_triggers_slack_event(self, client, db_session, monkeypatch):
        tenant_id = "integrations_lead_slack@example.com"
        headers = _jwt_headers(tenant_id)
        _seed_tenant(db_session, tenant_id)
        bot = _create_bot(client, headers, name="Slack Lead Bot")

        client.post(
            f"/api/v1/integrations/bots/{bot['id']}/integrations",
            json={
                "integration_type": "slack",
                "config": {"webhook_url": "https://hooks.slack.test/services/demo"},
                "is_active": True,
            },
            headers=headers,
        )

        calls = []

        def fake_notify(**kwargs):
            calls.append(kwargs)
            return True

        monkeypatch.setattr(integration_service, "notify_slack_event", fake_notify)

        conv = client.post(
            "/api/v1/dashboard/conversations",
            json={"bot_id": bot["id"]},
            headers=headers,
        )
        assert conv.status_code == 200

        resp = client.post(
            "/api/v1/leads/submit",
            json={
                "bot_id": bot["id"],
                "conversation_id": conv.json()["id"],
                "data": {"name": "Alice", "email": "alice@example.com"},
                "country": "US",
                "source": "Widget",
            },
        )
        assert resp.status_code == 200
        assert len(calls) == 1
        assert calls[0]["event_type"] == "lead_captured"
        assert calls[0]["bot_id"] == bot["id"]

    def test_transfer_rule_chat_triggers_slack_event(self, client, db_session, monkeypatch):
        tenant_id = "integrations_transfer_slack@example.com"
        headers = _jwt_headers(tenant_id)
        _seed_tenant(db_session, tenant_id)
        bot = _create_bot(client, headers, name="Slack Transfer Bot")

        client.post(
            f"/api/v1/integrations/bots/{bot['id']}/integrations",
            json={
                "integration_type": "slack",
                "config": {"webhook_url": "https://hooks.slack.test/services/demo"},
                "is_active": True,
            },
            headers=headers,
        )

        create_rule = client.post(
            f"/api/v1/agent-transfer/bots/{bot['id']}/rules",
            json={
                "name": "Escalate Billing",
                "rule_type": "keyword",
                "condition": "refund,chargeback",
                "action": "transfer",
                "transfer_message": "Connecting you to billing support.",
                "is_active": True,
                "priority": 1,
            },
            headers=headers,
        )
        assert create_rule.status_code == 200

        calls = []

        def fake_notify(**kwargs):
            calls.append(kwargs)
            return True

        monkeypatch.setattr(integration_service, "notify_slack_event", fake_notify)

        chat = client.post(
            "/api/v1/chat/",
            json={"bot_id": bot["id"], "message": "I need a refund right now"},
            headers=headers,
        )
        assert chat.status_code == 200
        payload = chat.json()
        assert "Connecting you to billing support." in payload["answer"]
        assert len(calls) == 1
        assert calls[0]["event_type"] == "transfer_rule_triggered"
        assert calls[0]["bot_id"] == bot["id"]
