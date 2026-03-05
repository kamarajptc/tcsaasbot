from app.core.database import TenantDB, TenantUsageDB, StripeEventDB
from app.core.security import create_access_token
from app.services.billing_service import billing_service


def _jwt_headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


def _create_tenant(db_session, tenant_id: str, plan: str = "starter"):
    tenant = TenantDB(id=tenant_id, name=f"Tenant {tenant_id}", plan=plan, is_active=True)
    db_session.add(tenant)
    db_session.commit()
    return tenant


def _create_bot(client, headers, name="Quota Bot"):
    resp = client.post(
        "/api/v1/dashboard/",
        json={
            "name": name,
            "description": "bot for quota tests",
            "prompt_template": "You are helpful.",
            "welcome_message": "Hi",
            "primary_color": "#2563eb",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


class TestQuotaEnforcement:
    def test_chat_blocks_when_message_quota_exceeded(self, client, db_session):
        tenant_id = "quota_chat_tenant@example.com"
        headers = _jwt_headers(tenant_id)
        _create_tenant(db_session, tenant_id, plan="starter")
        _create_bot(client, headers)
        db_session.add(TenantUsageDB(tenant_id=tenant_id, messages_sent=100, documents_indexed=0))
        db_session.commit()

        resp = client.post("/api/v1/chat/", json={"message": "hello"}, headers=headers)
        assert resp.status_code == 403
        assert "Message quota exceeded" in resp.json()["detail"]

    def test_ingest_blocks_when_document_quota_exceeded(self, client, db_session):
        tenant_id = "quota_docs_tenant@example.com"
        headers = _jwt_headers(tenant_id)
        _create_tenant(db_session, tenant_id, plan="starter")
        db_session.add(TenantUsageDB(tenant_id=tenant_id, messages_sent=0, documents_indexed=5))
        db_session.commit()

        resp = client.post(
            "/api/v1/ingest/",
            json={"text": "private docs", "metadata": {"title": "Doc A", "source": "unit"}},
            headers=headers,
        )
        assert resp.status_code == 403
        assert "Document quota exceeded" in resp.json()["detail"]

    def test_scrape_blocks_when_document_quota_exceeded(self, client, db_session):
        tenant_id = "quota_scrape_tenant@example.com"
        headers = _jwt_headers(tenant_id)
        _create_tenant(db_session, tenant_id, plan="starter")
        db_session.add(TenantUsageDB(tenant_id=tenant_id, messages_sent=0, documents_indexed=5))
        db_session.commit()

        resp = client.post(
            "/api/v1/ingest/scrape",
            json={"url": "https://example.com"},
            headers=headers,
        )
        assert resp.status_code == 403
        assert "Document quota exceeded" in resp.json()["detail"]


class TestBillingReadiness:
    def test_checkout_fails_with_clear_error_when_stripe_not_configured(self, client, db_session, monkeypatch):
        tenant_id = "billing_missing_config@example.com"
        headers = _jwt_headers(tenant_id)
        _create_tenant(db_session, tenant_id, plan="starter")

        monkeypatch.setattr("app.services.billing_service.settings.STRIPE_SECRET_KEY", "")
        monkeypatch.setattr("app.services.billing_service.settings.STRIPE_PRICE_PRO_ID", "")

        resp = client.post("/api/v1/billing/checkout", json={"plan": "pro"}, headers=headers)
        assert resp.status_code == 400
        assert "Stripe is not configured" in resp.json()["detail"]

    def test_webhook_processing_is_idempotent(self, db_session, monkeypatch):
        tenant_id = "billing_idempotency@example.com"
        _create_tenant(db_session, tenant_id, plan="starter")

        monkeypatch.setattr("app.services.billing_service.settings.STRIPE_SECRET_KEY", "sk_test_realish")
        monkeypatch.setattr("app.services.billing_service.settings.STRIPE_WEBHOOK_SECRET", "whsec_realish")

        event = {
            "id": "evt_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "subscription": "sub_123",
                    "metadata": {"tenant_id": tenant_id, "plan": "pro"},
                }
            },
        }

        def fake_construct_event(payload, sig_header, secret):
            return event

        monkeypatch.setattr("app.services.billing_service.stripe.Webhook.construct_event", fake_construct_event)

        assert billing_service.handle_webhook(db_session, b"{}", "sig") is True
        assert billing_service.handle_webhook(db_session, b"{}", "sig") is True

        tenant = db_session.query(TenantDB).filter(TenantDB.id == tenant_id).first()
        assert tenant.plan == "pro"
        assert tenant.stripe_subscription_id == "sub_123"
        assert db_session.query(StripeEventDB).filter(StripeEventDB.event_id == "evt_123").count() == 1
