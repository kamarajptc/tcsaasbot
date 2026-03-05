from app.core.security import create_access_token


def _headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


TENANT_A = _headers("rt_a@example.com")
TENANT_B = _headers("rt_b@example.com")


def _create_bot(client, headers, name: str):
    resp = client.post(
        "/api/v1/dashboard/",
        json={"name": name, "description": "rt report bot"},
        headers=headers,
    )
    assert resp.status_code in (200, 201)
    return resp.json()["id"]


def _create_conversation(client, headers, bot_id: int):
    resp = client.post("/api/v1/dashboard/conversations", json={"bot_id": bot_id}, headers=headers)
    assert resp.status_code == 200
    return resp.json()["id"]


class TestCustomersRealtime:
    def test_realtime_report_returns_summary_and_rows(self, client):
        bot_id = _create_bot(client, TENANT_A, "Realtime Bot A")
        conv_id = _create_conversation(client, TENANT_A, bot_id)

        client.post(
            "/api/v1/chat/",
            json={"bot_id": bot_id, "conversation_id": conv_id, "message": "Need pricing support"},
            headers=TENANT_A,
        )

        res = client.get("/api/v1/analytics/customers/realtime?status=all&limit=20", headers=TENANT_A)
        assert res.status_code == 200
        payload = res.json()
        assert "summary" in payload
        assert "items" in payload
        assert payload["summary"]["total_customers"] >= 1
        assert isinstance(payload["items"], list)
        assert payload["items"][0]["conversation_id"] == conv_id

    def test_realtime_report_is_tenant_scoped(self, client):
        bot_a = _create_bot(client, TENANT_A, "Realtime A")
        bot_b = _create_bot(client, TENANT_B, "Realtime B")
        _create_conversation(client, TENANT_A, bot_a)
        _create_conversation(client, TENANT_B, bot_b)

        rows_a = client.get("/api/v1/analytics/customers/realtime", headers=TENANT_A)
        rows_b = client.get("/api/v1/analytics/customers/realtime", headers=TENANT_B)
        assert rows_a.status_code == 200
        assert rows_b.status_code == 200
        assert len(rows_a.json()["items"]) == 1
        assert len(rows_b.json()["items"]) == 1
        assert rows_a.json()["items"][0]["bot_name"] == "Realtime A"
        assert rows_b.json()["items"][0]["bot_name"] == "Realtime B"

