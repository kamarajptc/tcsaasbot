import json

from app.core.security import create_access_token


def _headers(tenant_id: str, role: str = "admin"):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


TENANT_A_ADMIN = _headers("quality_a@example.com", "admin")
TENANT_A_EDITOR = _headers("quality_a@example.com", "editor")
TENANT_A_VIEWER = _headers("quality_a@example.com", "viewer")
TENANT_B_ADMIN = _headers("quality_b@example.com", "admin")


def _create_bot(client, headers):
    resp = client.post(
        "/api/v1/dashboard/",
        json={"name": "Quality Bot", "description": "quality"},
        headers=headers,
    )
    assert resp.status_code in (200, 201)
    return resp.json()["id"]


def test_quality_service_status_and_rbac_me(client):
    _create_bot(client, TENANT_A_ADMIN)
    me = client.get("/api/v1/quality/rbac/me", headers=TENANT_A_VIEWER)
    assert me.status_code == 200
    assert me.json()["tenant_id"] == "quality_a@example.com"
    assert me.json()["role"] == "viewer"

    status = client.get("/api/v1/quality/status/services", headers=TENANT_A_VIEWER)
    assert status.status_code == 200
    assert any(x["service"] == "backend" for x in status.json()["items"])


def test_quality_viewer_cannot_edit_release_or_run_tests(client):
    _create_bot(client, TENANT_A_ADMIN)
    run = client.post("/api/v1/quality/tests/run", json={"full": True}, headers=TENANT_A_VIEWER)
    assert run.status_code == 403

    checklist = client.put(
        "/api/v1/quality/release/checklist",
        json={"tests_green": True},
        headers=TENANT_A_VIEWER,
    )
    assert checklist.status_code == 403


def test_quality_editor_can_queue_tests_and_update_checklist(client, monkeypatch):
    _create_bot(client, TENANT_A_ADMIN)

    def _fake_create_task(coro):
        coro.close()
        return None

    monkeypatch.setattr("app.api.v1.quality.asyncio.create_task", _fake_create_task)

    run = client.post(
        "/api/v1/quality/tests/run",
        json={"full": True, "include_security_lane": True, "parallel": False, "max_fail": 0},
        headers=TENANT_A_EDITOR,
    )
    assert run.status_code == 200
    assert run.json()["status"] == "queued"

    update = client.put(
        "/api/v1/quality/release/checklist",
        json={"tests_green": True, "rollback_ready": True},
        headers=TENANT_A_EDITOR,
    )
    assert update.status_code == 200
    assert update.json()["checklist"]["tests_green"] is True
    assert update.json()["checklist"]["rollback_ready"] is True


def test_quality_admin_only_evidence_and_retention(client):
    _create_bot(client, TENANT_A_ADMIN)
    denied = client.get("/api/v1/quality/release/evidence", headers=TENANT_A_EDITOR)
    assert denied.status_code == 403

    ok = client.get("/api/v1/quality/release/evidence", headers=TENANT_A_ADMIN)
    assert ok.status_code == 200
    assert ok.json()["path"].endswith("evidence_bundle.zip")

    retention_denied = client.post("/api/v1/quality/retention/apply?days=30", headers=TENANT_A_EDITOR)
    assert retention_denied.status_code == 403
    retention_ok = client.post("/api/v1/quality/retention/apply?days=30", headers=TENANT_A_ADMIN)
    assert retention_ok.status_code == 200


def test_quality_tenant_isolation_for_test_artifacts(client):
    _create_bot(client, TENANT_A_ADMIN)
    _create_bot(client, TENANT_B_ADMIN)
    from app.api.v1.quality import _latest_dir

    latest_a = _latest_dir("quality_a@example.com")
    latest_a.mkdir(parents=True, exist_ok=True)
    (latest_a / "summary.json").write_text(
        json.dumps(
            {
                "pytest": {"total": 10, "passed": 10, "failed": 0, "errors": 0, "modules": [], "failures": []},
                "coverage": {"coverage_pct": 88.4, "source": "proxy"},
            }
        )
    )

    own = client.get("/api/v1/quality/tests/latest", headers=TENANT_A_ADMIN)
    assert own.status_code == 200
    assert own.json()["summary"]["pytest"]["total"] == 10

    foreign = client.get("/api/v1/quality/tests/latest", headers=TENANT_B_ADMIN)
    assert foreign.status_code == 200
    assert foreign.json()["summary"] == {}


def test_quality_observability_panels_return_expected_shapes(client):
    _create_bot(client, TENANT_A_ADMIN)
    metrics = client.get("/api/v1/quality/observability/metrics", headers=TENANT_A_VIEWER)
    logs = client.get("/api/v1/quality/observability/logs?limit=5", headers=TENANT_A_VIEWER)
    traces = client.get("/api/v1/quality/observability/traces?limit=5", headers=TENANT_A_VIEWER)
    alerts = client.get("/api/v1/quality/observability/alerts", headers=TENANT_A_VIEWER)
    coverage = client.get("/api/v1/quality/tests/coverage", headers=TENANT_A_VIEWER)
    risk = client.get("/api/v1/quality/release/risk", headers=TENANT_A_VIEWER)

    assert metrics.status_code == 200
    assert "latency_p95_ms" in metrics.json()
    assert logs.status_code == 200
    assert isinstance(logs.json()["items"], list)
    assert traces.status_code == 200
    assert isinstance(traces.json()["items"], list)
    assert alerts.status_code == 200
    assert isinstance(alerts.json()["items"], list)
    assert coverage.status_code == 200
    assert "gate_passed" in coverage.json()
    assert risk.status_code == 200
    assert "risk_score" in risk.json()


def test_quality_security_checklist_endpoint(client):
    _create_bot(client, TENANT_A_ADMIN)
    resp = client.get("/api/v1/quality/security/checklist", headers=TENANT_A_VIEWER)
    assert resp.status_code == 200
    payload = resp.json()
    assert "checks" in payload
    assert isinstance(payload["checks"], list)
    assert all("name" in c and "passed" in c for c in payload["checks"])
