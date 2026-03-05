from jose import jwt
from datetime import datetime, timedelta
import logging
import pytest

from app.core.config import get_settings
from app.core.config import Settings
from app.core.database import TenantDB, ConversationDB, MessageDB
from app.core.security import create_access_token


def _seed_tenant(db_session, tenant_id: str):
    tenant = TenantDB(id=tenant_id, name=f"Tenant {tenant_id}", plan="starter", is_active=True)
    db_session.add(tenant)
    db_session.commit()


def _bearer_headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


class TestAuthSecurity:
    def test_login_requires_valid_password(self, client, db_session):
        _seed_tenant(db_session, "secure_tenant@example.com")

        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "secure_tenant@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401
        assert "Invalid credentials" in resp.json()["detail"]

    def test_login_requires_existing_tenant(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "missing_tenant@example.com", "password": "password123"},
        )
        assert resp.status_code == 401
        assert "Unknown tenant" in resp.json()["detail"]

    def test_login_returns_jwt_with_security_claims(self, client, db_session):
        settings = get_settings()
        _seed_tenant(db_session, "tenant_claims@example.com")

        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "tenant_claims@example.com", "password": "password123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_type"] == "bearer"

        payload = jwt.decode(
            data["access_token"],
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
        assert payload["tenant_id"] == "tenant_claims@example.com"
        assert payload["sub"] == "tenant_claims@example.com"
        assert payload.get("jti")
        assert payload.get("iat")
        assert payload.get("nbf")

    def test_protected_route_rejects_missing_auth(self, client):
        resp = client.get("/api/v1/dashboard/")
        assert resp.status_code == 401

    def test_protected_route_rejects_invalid_token(self, client):
        resp = client.get("/api/v1/dashboard/", headers={"Authorization": "Bearer invalid.token.value"})
        assert resp.status_code == 401

    def test_protected_route_rejects_expired_token(self, client, db_session):
        settings = get_settings()
        tenant_id = "tenant_expired@example.com"
        _seed_tenant(db_session, tenant_id)
        token = create_access_token(
            {"sub": tenant_id, "tenant_id": tenant_id},
            expires_delta=timedelta(minutes=-5),
        )
        resp = client.get("/api/v1/dashboard/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_protected_route_rejects_missing_issuer_or_audience(self, client, db_session):
        settings = get_settings()
        tenant_id = "tenant_legacy_claims@example.com"
        _seed_tenant(db_session, tenant_id)
        token = jwt.encode(
            {"sub": tenant_id, "tenant_id": tenant_id},
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        resp = client.get("/api/v1/dashboard/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_protected_route_allows_valid_bearer(self, client, db_session):
        _seed_tenant(db_session, "tenant_alpha_001")
        resp = client.get("/api/v1/dashboard/settings", headers=_bearer_headers("tenant_alpha_001"))
        assert resp.status_code == 200
        assert resp.json()["id"] == "tenant_alpha_001"

    def test_missing_auth_attempt_is_audited(self, client, caplog):
        with caplog.at_level(logging.WARNING, logger="TangentCloud"):
            resp = client.get("/api/v1/dashboard/")
        assert resp.status_code == 401
        assert any("auth_missing_credentials" in rec.message for rec in caplog.records)

    def test_invalid_token_attempt_is_audited(self, client, caplog):
        with caplog.at_level(logging.WARNING, logger="TangentCloud"):
            resp = client.get("/api/v1/dashboard/", headers={"Authorization": "Bearer invalid.token.value"})
        assert resp.status_code == 401
        assert any("auth_invalid_token" in rec.message for rec in caplog.records)


class TestUiApiContracts:
    def test_conversation_payload_contains_ui_safe_keys(self, client, db_session):
        _seed_tenant(db_session, "tenant_ui_contract@example.com")
        headers = _bearer_headers("tenant_ui_contract@example.com")

        conv = ConversationDB(tenant_id="tenant_ui_contract@example.com", bot_id=None, created_at=datetime.utcnow())
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(conv)
        db_session.add(MessageDB(conversation_id=conv.id, sender="user", text="Hello there"))
        db_session.commit()

        conv_list = client.get("/api/v1/dashboard/conversations", headers=headers)
        assert conv_list.status_code == 200
        rows = conv_list.json()
        assert isinstance(rows, list)
        if rows:
            row = rows[0]
            assert "id" in row
            assert "bot_name" in row
            assert "last_message" in row
            assert "message_count" in row


class TestProductionSecurityConfig:
    def test_production_rejects_default_auth_and_secret(self):
        with pytest.raises(ValueError):
            Settings(ENV="production")

    def test_production_accepts_non_default_secrets(self):
        cfg = Settings(
            ENV="production",
            AUTH_PASSWORD="A-Strong-Password-123",
            SECRET_KEY="A_LONG_NON_DEFAULT_SECRET_KEY_1234567890",
        )
        assert cfg.ENV == "production"
