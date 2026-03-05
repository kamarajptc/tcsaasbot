from app.core.database import TenantDB, RateLimitPolicyDB, TenantAlertSettingsDB
from app.core.security import create_access_token
from app.core.rate_limit import _policy_cache
from app.services.email_service import email_service
from app.services.integration_service import integration_service


def _headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


def _role_headers(tenant_id: str, role: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


def _seed_tenant(db_session, tenant_id: str, plan: str = "starter"):
    db_session.add(TenantDB(id=tenant_id, name=f"Tenant {tenant_id}", plan=plan, is_active=True))
    db_session.commit()


def test_dashboard_settings_exposes_effective_rate_limits(client, db_session):
    tenant_id = "rate_settings@example.com"
    _seed_tenant(db_session, tenant_id, plan="pro")
    db_session.add(RateLimitPolicyDB(plan="pro", route_key="chat", rpm_limit=90, is_active=True))
    db_session.add(RateLimitPolicyDB(plan="pro", route_key="default", rpm_limit=180, is_active=True))
    db_session.commit()
    _policy_cache.clear()

    resp = client.get("/api/v1/dashboard/settings", headers=_headers(tenant_id))
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["rate_limits"]["chat"] == 90
    assert payload["rate_limits"]["default"] == 180


def test_tenant_specific_policy_drives_429_contract_and_metrics(client, db_session):
    tenant_id = "rate_contract@example.com"
    _seed_tenant(db_session, tenant_id, plan="starter")
    db_session.add(RateLimitPolicyDB(tenant_id=tenant_id, route_key="dashboard_conversations", rpm_limit=1, is_active=True))
    db_session.commit()
    _policy_cache.clear()

    headers = _headers(tenant_id)
    first = client.get("/api/v1/dashboard/conversations", headers=headers)
    assert first.status_code == 200

    second = client.get("/api/v1/dashboard/conversations", headers=headers)
    assert second.status_code == 429
    body = second.json()
    assert body["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert body["tenant_id"] == tenant_id
    assert body["route_key"] == "dashboard_conversations"
    assert body["limit"] == 1
    assert "support" in body
    assert second.headers["X-RateLimit-Limit"] == "1"

    summary = client.get("/api/v1/analytics/rate-limits/summary", headers=headers)
    assert summary.status_code == 200
    metrics = summary.json()
    assert metrics["total_throttled_requests"] >= 1
    assert metrics["top_throttled_routes"][0]["route_key"] == "dashboard_conversations"
    assert metrics["recent_events"][0]["route_key"] == "dashboard_conversations"


def test_admin_policy_crud_and_duplicate_guard(client, db_session):
    _seed_tenant(db_session, "admin@example.com", plan="enterprise")
    admin_headers = _role_headers("admin@example.com", "admin")

    create_resp = client.post(
        "/api/v1/analytics/rate-limits/policies",
        json={"plan": "pro", "route_key": "chat_public", "rpm_limit": 55, "is_active": True},
        headers=admin_headers,
    )
    assert create_resp.status_code == 200
    policy_id = create_resp.json()["id"]
    assert create_resp.json()["scope"] == "plan"

    duplicate = client.post(
        "/api/v1/analytics/rate-limits/policies",
        json={"plan": "pro", "route_key": "chat_public", "rpm_limit": 99, "is_active": True},
        headers=admin_headers,
    )
    assert duplicate.status_code == 409

    listed = client.get("/api/v1/analytics/rate-limits/policies?plan=pro&route_key=chat_public", headers=admin_headers)
    assert listed.status_code == 200
    assert any(item["id"] == policy_id for item in listed.json()["items"])

    update_resp = client.put(
        f"/api/v1/analytics/rate-limits/policies/{policy_id}",
        json={"tenant_id": "tenant_override@example.com", "route_key": "chat_public", "rpm_limit": 77, "is_active": True},
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["scope"] == "tenant"
    assert update_resp.json()["tenant_id"] == "tenant_override@example.com"

    delete_resp = client.delete(f"/api/v1/analytics/rate-limits/policies/{policy_id}", headers=admin_headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True


def test_non_admin_cannot_manage_rate_limit_policies(client, db_session):
    _seed_tenant(db_session, "editor@example.com", plan="pro")
    editor_headers = _role_headers("editor@example.com", "editor")

    resp = client.get("/api/v1/analytics/rate-limits/policies", headers=editor_headers)
    assert resp.status_code == 403


def test_policy_changes_invalidate_cache_and_dashboard_overview_updates(client, db_session):
    tenant_id = "cached_limits@example.com"
    _seed_tenant(db_session, tenant_id, plan="starter")
    _seed_tenant(db_session, "admin@example.com", plan="enterprise")
    db_session.add(RateLimitPolicyDB(plan="starter", route_key="chat", rpm_limit=30, is_active=True))
    db_session.add(RateLimitPolicyDB(plan="starter", route_key="default", rpm_limit=60, is_active=True))
    db_session.commit()
    admin_headers = _role_headers("admin@example.com", "admin")
    user_headers = _headers(tenant_id)
    _policy_cache.clear()

    initial = client.get("/api/v1/dashboard/settings", headers=user_headers)
    assert initial.status_code == 200
    assert initial.json()["rate_limits"]["chat"] == 30

    create_resp = client.post(
        "/api/v1/analytics/rate-limits/policies",
        json={"tenant_id": tenant_id, "route_key": "chat", "rpm_limit": 5, "is_active": True},
        headers=admin_headers,
    )
    assert create_resp.status_code == 200

    refreshed = client.get("/api/v1/dashboard/settings", headers=user_headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["rate_limits"]["chat"] == 5
    assert refreshed.json()["support"]["email"]

    overview = client.get("/api/v1/dashboard/rate-limits", headers=user_headers)
    assert overview.status_code == 200
    assert overview.json()["effective_limits"]["chat"] == 5
    assert "support" in overview.json()


def test_repeated_throttle_alerts_include_escalation_metadata(client, db_session):
    tenant_id = "throttle-alert@example.com"
    _seed_tenant(db_session, tenant_id, plan="starter")
    _seed_tenant(db_session, "ops-admin@example.com", plan="enterprise")
    db_session.add(RateLimitPolicyDB(tenant_id=tenant_id, route_key="dashboard_conversations", rpm_limit=1, is_active=True))
    db_session.commit()
    _policy_cache.clear()

    user_headers = _headers(tenant_id)
    admin_headers = _role_headers("ops-admin@example.com", "admin")

    for _ in range(6):
        client.get("/api/v1/dashboard/conversations", headers=user_headers)

    alerts = client.get("/api/v1/analytics/rate-limits/alerts?window_hours=24&min_hits=3", headers=admin_headers)
    assert alerts.status_code == 200
    items = alerts.json()["items"]
    assert items
    first = items[0]
    assert first["tenant_id"] == tenant_id
    assert first["route_key"] == "dashboard_conversations"
    assert first["severity"] in {"medium", "high"}
    assert "next_action" in first
    assert "support" in first


def test_admin_can_manage_alert_notification_settings(client, db_session):
    tenant_id = "alert-settings-admin@example.com"
    _seed_tenant(db_session, tenant_id, plan="enterprise")
    headers = _role_headers(tenant_id, "admin")

    get_resp = client.get("/api/v1/analytics/rate-limits/notifications", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["rate_limit_min_hits"] >= 1

    put_resp = client.put(
        "/api/v1/analytics/rate-limits/notifications",
        json={
            "rate_limit_email_enabled": True,
            "rate_limit_email_recipient": "ops@example.com",
            "rate_limit_webhook_enabled": True,
            "rate_limit_webhook_url": "https://hooks.example.test/rate-limit",
            "rate_limit_min_hits": 2,
            "rate_limit_window_minutes": 30,
            "rate_limit_cooldown_minutes": 15,
        },
        headers=headers,
    )
    assert put_resp.status_code == 200
    payload = put_resp.json()
    assert payload["rate_limit_email_enabled"] is True
    assert payload["rate_limit_webhook_enabled"] is True

    admin_get = client.get("/api/v1/admin/rate-limits/notifications", headers=headers)
    assert admin_get.status_code == 200
    assert admin_get.json()["rate_limit_email_enabled"] is True


def test_high_severity_alerts_trigger_email_and_webhook_once_per_cooldown(client, db_session, monkeypatch):
    tenant_id = "alert-delivery@example.com"
    _seed_tenant(db_session, tenant_id, plan="starter")
    db_session.add(RateLimitPolicyDB(tenant_id=tenant_id, route_key="dashboard_conversations", rpm_limit=1, is_active=True))
    db_session.add(
        TenantAlertSettingsDB(
            tenant_id=tenant_id,
            rate_limit_email_enabled=True,
            rate_limit_email_recipient="ops@example.com",
            rate_limit_webhook_enabled=True,
            rate_limit_webhook_url="https://hooks.example.test/rate-limit",
            rate_limit_min_hits=2,
            rate_limit_window_minutes=60,
            rate_limit_cooldown_minutes=60,
        )
    )
    db_session.commit()
    _policy_cache.clear()

    email_calls = []
    webhook_calls = []

    def fake_send_email(db, tenant_id, subject, body, recipient=None):
        email_calls.append({"tenant_id": tenant_id, "subject": subject, "recipient": recipient})
        return True

    def fake_webhook(url, payload, max_attempts=3):
        webhook_calls.append({"url": url, "payload": payload})
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send_email)
    monkeypatch.setattr(integration_service, "post_json_webhook", fake_webhook)

    headers = _headers(tenant_id)
    first = client.get("/api/v1/dashboard/conversations", headers=headers)
    assert first.status_code == 200

    second = client.get("/api/v1/dashboard/conversations", headers=headers)
    assert second.status_code == 429

    third = client.get("/api/v1/dashboard/conversations", headers=headers)
    assert third.status_code == 429
    assert len(email_calls) == 1
    assert len(webhook_calls) == 1

    fourth = client.get("/api/v1/dashboard/conversations", headers=headers)
    assert fourth.status_code == 429
    assert len(email_calls) == 1
    assert len(webhook_calls) == 1

    deliveries = client.get("/api/v1/admin/rate-limits/deliveries", headers=_role_headers(tenant_id, "admin"))
    assert deliveries.status_code == 200
    items = deliveries.json()["items"]
    assert len(items) == 2
    assert {item["channel"] for item in items} == {"email", "webhook"}


def test_admin_policy_endpoints_available_under_dedicated_admin_api(client, db_session):
    tenant_id = "admin-api@example.com"
    _seed_tenant(db_session, tenant_id, plan="enterprise")
    headers = _role_headers(tenant_id, "admin")

    create_resp = client.post(
        "/api/v1/admin/rate-limits/policies",
        json={"plan": "starter", "route_key": "auth", "rpm_limit": 12, "is_active": True},
        headers=headers,
    )
    assert create_resp.status_code == 200
    policy_id = create_resp.json()["id"]

    list_resp = client.get("/api/v1/admin/rate-limits/policies?plan=starter&route_key=auth", headers=headers)
    assert list_resp.status_code == 200
    assert any(item["id"] == policy_id for item in list_resp.json()["items"])


def test_admin_audit_trail_records_policy_and_notification_changes(client, db_session):
    tenant_id = "audit-admin@example.com"
    _seed_tenant(db_session, tenant_id, plan="enterprise")
    headers = _role_headers(tenant_id, "admin")

    create_resp = client.post(
        "/api/v1/admin/rate-limits/policies",
        json={"tenant_id": tenant_id, "route_key": "chat", "rpm_limit": 44, "is_active": True},
        headers=headers,
    )
    assert create_resp.status_code == 200

    notify_resp = client.put(
        "/api/v1/admin/rate-limits/notifications",
        json={
            "rate_limit_email_enabled": True,
            "rate_limit_email_recipient": "audit@example.com",
            "rate_limit_webhook_enabled": False,
            "rate_limit_webhook_url": None,
            "rate_limit_min_hits": 3,
            "rate_limit_window_minutes": 30,
            "rate_limit_cooldown_minutes": 30,
        },
        headers=headers,
    )
    assert notify_resp.status_code == 200

    audit_resp = client.get("/api/v1/admin/rate-limits/audit?limit=10", headers=headers)
    assert audit_resp.status_code == 200
    payload = audit_resp.json()
    assert payload["pagination"]["total"] >= 2
    actions = [item["action"] for item in payload["items"]]
    assert "rate_limit_policy_created" in actions
    assert "rate_limit_notification_settings_updated" in actions
