from app.core.database import ConversationDB, MessageDB, TenantDB
from app.core.security import create_access_token


def _jwt_headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


def _seed_tenant(db_session, tenant_id: str):
    tenant = TenantDB(id=tenant_id, name=f"Tenant {tenant_id}", plan="starter", is_active=True)
    db_session.add(tenant)
    db_session.commit()


def _create_bot(client, headers, name="Suggest Bot"):
    resp = client.post(
        "/api/v1/dashboard/",
        json={
            "name": name,
            "description": "bot for suggestion tests",
            "prompt_template": "You are helpful.",
            "welcome_message": "Hi",
            "primary_color": "#2563eb",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


class TestFaqSuggestionPipeline:
    def test_suggestions_generated_from_unresolved_questions(self, client, db_session):
        tenant_id = "suggestions@example.com"
        headers = _jwt_headers(tenant_id)
        _seed_tenant(db_session, tenant_id)
        bot = _create_bot(client, headers)

        conv = ConversationDB(tenant_id=tenant_id, bot_id=bot["id"])
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)

        db_session.add_all([
            MessageDB(conversation_id=conv.id, sender="user", text="What is your refund policy?"),
            MessageDB(conversation_id=conv.id, sender="bot", text="That information is not available right now."),
            MessageDB(conversation_id=conv.id, sender="user", text="Do you have a mobile app?"),
        ])
        db_session.commit()

        resp = client.get(f"/api/v1/analytics/faq-suggestions?bot_id={bot['id']}&limit=5", headers=headers)
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) >= 1
        assert any("refund policy" in row["question"].lower() or "mobile app" in row["question"].lower() for row in rows)

    def test_suggestions_are_tenant_isolated(self, client, db_session):
        tenant_a = "suggest_a@example.com"
        tenant_b = "suggest_b@example.com"
        headers_a = _jwt_headers(tenant_a)
        headers_b = _jwt_headers(tenant_b)
        _seed_tenant(db_session, tenant_a)
        _seed_tenant(db_session, tenant_b)
        bot_a = _create_bot(client, headers_a, name="A")
        _create_bot(client, headers_b, name="B")

        conv_a = ConversationDB(tenant_id=tenant_a, bot_id=bot_a["id"])
        db_session.add(conv_a)
        db_session.commit()
        db_session.refresh(conv_a)
        db_session.add(MessageDB(conversation_id=conv_a.id, sender="user", text="Where is my invoice?"))
        db_session.commit()

        resp_b = client.get("/api/v1/analytics/faq-suggestions?limit=5", headers=headers_b)
        assert resp_b.status_code == 200
        assert resp_b.json() == []
