"""Tests for Bot Workspace -> Live Chat screen workflows."""

from app.core.security import create_access_token


def _jwt_headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


TENANT_A = _jwt_headers("tenant_alpha_001")
TENANT_B = _jwt_headers("tenant_beta_002")


def _create_bot(client, name: str, headers=None):
    headers = headers or TENANT_A
    resp = client.post(
        "/api/v1/dashboard/",
        json={
            "name": name,
            "description": "screen test bot",
            "prompt_template": "You are a helpful assistant.",
            "welcome_message": "Hi! How can I help?",
            "primary_color": "#2563eb",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


def _create_conversation(client, bot_id: int, headers=None):
    headers = headers or TENANT_A
    resp = client.post(
        "/api/v1/dashboard/conversations",
        json={"bot_id": bot_id},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


class TestLiveChatScreenFlow:
    def test_inbox_starts_empty(self, client):
        resp = client.get("/api/v1/dashboard/conversations", headers=TENANT_A)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_plus_button_flow_create_conversation(self, client):
        bot = _create_bot(client, "LiveChat Bot")
        created = _create_conversation(client, bot["id"])

        assert created["bot_id"] == bot["id"]
        assert created["bot_name"] == bot["name"]
        assert created["status"] == "new"
        assert created["message_count"] == 0
        assert created["last_message"] == "No messages"

        inbox = client.get("/api/v1/dashboard/conversations", headers=TENANT_A)
        assert inbox.status_code == 200
        assert len(inbox.json()) == 1
        assert inbox.json()[0]["id"] == created["id"]

    def test_select_conversation_loads_messages(self, client):
        bot = _create_bot(client, "Select Flow Bot")
        conv = _create_conversation(client, bot["id"])

        resp = client.get(
            f"/api/v1/dashboard/conversations/{conv['id']}/messages",
            headers=TENANT_A,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_send_agent_message_and_refresh_messages(self, client):
        bot = _create_bot(client, "Agent Reply Bot")
        conv = _create_conversation(client, bot["id"])

        send_resp = client.post(
            f"/api/v1/chat/conversations/{conv['id']}/messages",
            json={"message": "Hello from human agent"},
            headers=TENANT_A,
        )
        assert send_resp.status_code == 200
        sent = send_resp.json()
        assert sent["id"] > 0
        assert sent["sender"] == "agent"
        assert sent["text"] == "Hello from human agent"

        list_resp = client.get(
            f"/api/v1/dashboard/conversations/{conv['id']}/messages",
            headers=TENANT_A,
        )
        assert list_resp.status_code == 200
        messages = list_resp.json()
        assert len(messages) == 1
        assert messages[0]["sender"] == "agent"
        assert messages[0]["text"] == "Hello from human agent"

        inbox_resp = client.get("/api/v1/dashboard/conversations", headers=TENANT_A)
        assert inbox_resp.status_code == 200
        inbox_row = next(item for item in inbox_resp.json() if item["id"] == conv["id"])
        assert inbox_row["last_message"] == "Hello from human agent"
        assert inbox_row["last_message_sender"] == "agent"
        assert inbox_row["message_count"] == 1

    def test_agent_reply_transitions_open_to_pending(self, client):
        bot = _create_bot(client, "Status Transition Bot")
        conv = _create_conversation(client, bot["id"])
        enable_transfer = client.put(
            f"/api/v1/dashboard/{bot['id']}",
            json={"agent_transfer_enabled": True},
            headers=TENANT_A,
        )
        assert enable_transfer.status_code == 200

        # Trigger transfer/open status.
        transfer = client.post(
            "/api/v1/chat/",
            json={"bot_id": bot["id"], "conversation_id": conv["id"], "message": "I need human help"},
            headers=TENANT_A,
        )
        assert transfer.status_code == 200

        before = client.get("/api/v1/dashboard/conversations", headers=TENANT_A)
        assert before.status_code == 200
        status_before = next(item for item in before.json() if item["id"] == conv["id"])["status"]
        assert status_before == "open"

        send_resp = client.post(
            f"/api/v1/chat/conversations/{conv['id']}/messages",
            json={"message": "Agent here, reviewing this now."},
            headers=TENANT_A,
        )
        assert send_resp.status_code == 200

        after = client.get("/api/v1/dashboard/conversations", headers=TENANT_A)
        assert after.status_code == 200
        status_after = next(item for item in after.json() if item["id"] == conv["id"])["status"]
        assert status_after == "pending"

    def test_conversation_list_supports_status_and_search_filters(self, client):
        bot = _create_bot(client, "Filter Bot")
        conv = _create_conversation(client, bot["id"])
        enable_transfer = client.put(
            f"/api/v1/dashboard/{bot['id']}",
            json={"agent_transfer_enabled": True},
            headers=TENANT_A,
        )
        assert enable_transfer.status_code == 200

        client.post(
            "/api/v1/chat/",
            json={"bot_id": bot["id"], "conversation_id": conv["id"], "message": "I need human help"},
            headers=TENANT_A,
        )

        client.post(
            f"/api/v1/chat/conversations/{conv['id']}/messages",
            json={"message": "Need invoice copy"},
            headers=TENANT_A,
        )

        filtered = client.get("/api/v1/dashboard/conversations?status=pending&q=invoice", headers=TENANT_A)
        assert filtered.status_code == 200
        payload = filtered.json()
        assert len(payload) == 1
        assert payload[0]["id"] == conv["id"]
        assert payload[0]["status"] == "pending"

    def test_clear_inbox_only_clears_selected_bot(self, client):
        bot_one = _create_bot(client, "Bot One")
        bot_two = _create_bot(client, "Bot Two")
        conv_one = _create_conversation(client, bot_one["id"])
        conv_two = _create_conversation(client, bot_two["id"])

        client.post(
            f"/api/v1/chat/conversations/{conv_one['id']}/messages",
            json={"message": "message for bot one"},
            headers=TENANT_A,
        )
        client.post(
            f"/api/v1/chat/conversations/{conv_two['id']}/messages",
            json={"message": "message for bot two"},
            headers=TENANT_A,
        )

        clear_resp = client.delete(
            f"/api/v1/dashboard/bots/{bot_one['id']}/conversations",
            headers=TENANT_A,
        )
        assert clear_resp.status_code == 200
        assert clear_resp.json()["ok"] is True
        assert clear_resp.json()["deleted_conversations"] == 1

        inbox_after = client.get("/api/v1/dashboard/conversations", headers=TENANT_A)
        assert inbox_after.status_code == 200
        remaining = inbox_after.json()
        assert len(remaining) == 1
        assert remaining[0]["bot_id"] == bot_two["id"]

    def test_clear_inbox_unknown_bot_returns_404(self, client):
        resp = client.delete("/api/v1/dashboard/bots/9999/conversations", headers=TENANT_A)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Bot not found"

    def test_cross_tenant_inbox_and_message_isolation(self, client):
        bot_a = _create_bot(client, "Tenant A Bot", headers=TENANT_A)
        conv_a = _create_conversation(client, bot_a["id"], headers=TENANT_A)

        # Tenant B should not see tenant A conversations.
        list_b = client.get("/api/v1/dashboard/conversations", headers=TENANT_B)
        assert list_b.status_code == 200
        assert list_b.json() == []

        # Tenant B should not read tenant A messages.
        msg_b = client.get(
            f"/api/v1/dashboard/conversations/{conv_a['id']}/messages",
            headers=TENANT_B,
        )
        assert msg_b.status_code == 404

        # Tenant B should not send agent message on tenant A conversation.
        send_b = client.post(
            f"/api/v1/chat/conversations/{conv_a['id']}/messages",
            json={"message": "unauthorized"},
            headers=TENANT_B,
        )
        assert send_b.status_code == 404
