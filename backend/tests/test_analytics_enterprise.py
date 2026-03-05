import time

from app.core.security import create_access_token


def _headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


TENANT_A = _headers("enterprise_a@example.com")
TENANT_B = _headers("enterprise_b@example.com")


def _create_bot(client, headers, name="Enterprise Bot"):
    resp = client.post(
        "/api/v1/dashboard/",
        json={
            "name": name,
            "description": "enterprise test bot",
            "prompt_template": "You are helpful",
            "welcome_message": "Hi",
            "primary_color": "#2563eb",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_conversation(client, headers, bot_id: int):
    resp = client.post("/api/v1/dashboard/conversations", json={"bot_id": bot_id}, headers=headers)
    assert resp.status_code == 200
    return resp.json()["id"]


class TestEnterpriseAnalytics:
    def test_metric_dictionary_and_report_pagination(self, client):
        bot_id = _create_bot(client, TENANT_A, "Paginated Bot")
        for _ in range(4):
            _create_conversation(client, TENANT_A, bot_id)

        md = client.get("/api/v1/analytics/enterprise/v1/metric-dictionary", headers=TENANT_A)
        assert md.status_code == 200
        assert md.json()["schema_version"] == "v1"
        assert len(md.json()["metrics"]) >= 1

        page1 = client.get(
            "/api/v1/analytics/enterprise/v1/report?report_type=overview&page=1&page_size=2",
            headers=TENANT_A,
        )
        assert page1.status_code == 200
        payload = page1.json()
        assert payload["pagination"]["total_items"] == 4
        assert len(payload["items"]) == 2

    def test_team_metrics_and_quality_insights_are_tenant_scoped(self, client):
        bot_a = _create_bot(client, TENANT_A, "Team Bot A")
        bot_b = _create_bot(client, TENANT_B, "Team Bot B")

        conv_a = _create_conversation(client, TENANT_A, bot_a)
        conv_b = _create_conversation(client, TENANT_B, bot_b)

        client.post(
            "/api/v1/chat/",
            json={"bot_id": bot_a, "conversation_id": conv_a, "message": "Need a refund"},
            headers=TENANT_A,
        )
        client.post(
            f"/api/v1/chat/conversations/{conv_a}/messages",
            json={"message": "Agent reply from tenant A"},
            headers=TENANT_A,
        )
        client.post(
            "/api/v1/chat/",
            json={"bot_id": bot_b, "conversation_id": conv_b, "message": "Need support"},
            headers=TENANT_B,
        )

        perf_a = client.get("/api/v1/analytics/enterprise/team/performance", headers=TENANT_A)
        assert perf_a.status_code == 200
        assert perf_a.json()["total_conversations"] >= 1

        quality_a = client.get("/api/v1/analytics/enterprise/quality/insights", headers=TENANT_A)
        assert quality_a.status_code == 200
        assert "unresolved_clusters" in quality_a.json()

        perf_b = client.get("/api/v1/analytics/enterprise/team/performance", headers=TENANT_B)
        assert perf_b.status_code == 200
        assert perf_b.json()["total_conversations"] >= 1

    def test_schedule_and_export_job_flow(self, client):
        _create_bot(client, TENANT_A, "Schedule Bot")
        create_sched = client.post(
            "/api/v1/analytics/enterprise/reports/schedules",
            json={
                "name": "Weekly Ops",
                "frequency": "weekly",
                "timezone": "UTC",
                "report_type": "overview",
                "recipient_email": "ops@example.com",
                "is_active": True,
            },
            headers=TENANT_A,
        )
        assert create_sched.status_code == 200
        schedule_id = create_sched.json()["id"]

        run = client.post(f"/api/v1/analytics/enterprise/reports/schedules/{schedule_id}/run", headers=TENANT_A)
        assert run.status_code == 200
        job_id = run.json()["job_id"]

        # background task may still be running
        time.sleep(0.05)
        job = client.get(f"/api/v1/analytics/enterprise/reports/exports/{job_id}", headers=TENANT_A)
        assert job.status_code == 200
        assert job.json()["status"] in {"queued", "processing", "completed"}

    def test_cross_tenant_export_job_access_is_blocked(self, client):
        _create_bot(client, TENANT_A, "Export Isolation Bot")
        create = client.post(
            "/api/v1/analytics/enterprise/reports/exports",
            json={"report_type": "overview", "filters": {}},
            headers=TENANT_A,
        )
        assert create.status_code == 200
        job_id = create.json()["job_id"]

        denied = client.get(f"/api/v1/analytics/enterprise/reports/exports/{job_id}", headers=TENANT_B)
        assert denied.status_code == 404
