from app.core.database import ConversationDB, MessageDB, TenantDB
from app.core.security import create_access_token


def _jwt_headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


def _seed_tenant(db_session, tenant_id: str):
    tenant = TenantDB(id=tenant_id, name=f"Tenant {tenant_id}", plan="starter", is_active=True)
    db_session.add(tenant)
    db_session.commit()


def _create_bot(client, headers, name="Transfer Bot"):
    resp = client.post(
        "/api/v1/dashboard/",
        json={
            "name": name,
            "description": "transfer test bot",
            "prompt_template": "You are helpful.",
            "welcome_message": "Hi",
            "primary_color": "#2563eb",
            "agent_transfer_enabled": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


class TestAgentTransferRules:
    def test_rule_crud_and_manual_trigger(self, client, db_session):
        tenant = "transfer_rules@example.com"
        headers = _jwt_headers(tenant)
        _seed_tenant(db_session, tenant)
        bot = _create_bot(client, headers)

        create = client.post(
            f"/api/v1/agent-transfer/bots/{bot['id']}/rules",
            json={
                "name": "Manual escalation",
                "rule_type": "manual",
                "condition": "agent-request",
                "action": "transfer",
                "transfer_message": "A human agent will join now.",
                "is_active": True,
            },
            headers=headers,
        )
        assert create.status_code == 200
        rule_id = create.json()["id"]

        listed = client.get(f"/api/v1/agent-transfer/bots/{bot['id']}/rules", headers=headers)
        assert listed.status_code == 200
        assert any(rule["id"] == rule_id for rule in listed.json())

        conv = ConversationDB(tenant_id=tenant, bot_id=bot["id"])
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)

        trigger = client.post(
            f"/api/v1/agent-transfer/conversations/{conv.id}/trigger",
            json={"rule_id": rule_id, "note": "VIP customer"},
            headers=headers,
        )
        assert trigger.status_code == 200
        db_session.refresh(conv)
        assert conv.agent_requested is True
        assert conv.status == "open"

        messages = db_session.query(MessageDB).filter(MessageDB.conversation_id == conv.id).all()
        assert any("human agent" in m.text.lower() for m in messages)

    def test_keyword_transfer_rule_triggers_from_chat(self, client, db_session):
        tenant = "transfer_chat@example.com"
        headers = _jwt_headers(tenant)
        _seed_tenant(db_session, tenant)
        bot = _create_bot(client, headers)

        create = client.post(
            f"/api/v1/agent-transfer/bots/{bot['id']}/rules",
            json={
                "name": "Refund escalation",
                "rule_type": "keyword",
                "condition": "refund,money back",
                "action": "transfer",
                "transfer_message": "Routing you to billing specialist.",
                "is_active": True,
            },
            headers=headers,
        )
        assert create.status_code == 200

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "I need a refund", "bot_id": bot["id"]},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "routing you to billing specialist" in data["answer"].lower()

        conv = db_session.query(ConversationDB).filter(ConversationDB.id == data["conversation_id"]).first()
        assert conv.agent_requested is True
        assert conv.status == "open"

    def test_notify_only_rule_executes_without_forcing_transfer(self, client, db_session, monkeypatch):
        tenant = "transfer_notify@example.com"
        headers = _jwt_headers(tenant)
        _seed_tenant(db_session, tenant)
        bot = _create_bot(client, headers)

        called = {"email": 0}

        def fake_send_email(*args, **kwargs):
            called["email"] += 1
            return True

        monkeypatch.setattr("app.api.v1.chat.email_service.send_email", fake_send_email)

        create = client.post(
            f"/api/v1/agent-transfer/bots/{bot['id']}/rules",
            json={
                "name": "Notify finance",
                "rule_type": "keyword",
                "condition": "invoice",
                "action": "notify",
                "notify_email": "finance@example.com",
                "is_active": True,
            },
            headers=headers,
        )
        assert create.status_code == 200

        resp = client.post(
            "/api/v1/chat/",
            json={"message": "I need an invoice copy", "bot_id": bot["id"]},
            headers=headers,
        )
        assert resp.status_code == 200
        assert called["email"] == 1

        conv = db_session.query(ConversationDB).filter(ConversationDB.id == resp.json()["conversation_id"]).first()
        assert conv.agent_requested is False
