from app.core.security import create_access_token


def _headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


def test_security_headers_present_on_public_route(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "frame-ancestors 'none'" in resp.headers.get("content-security-policy", "")


def test_security_headers_present_on_protected_route(client):
    headers = _headers("headers_tenant@example.com")
    create_bot = client.post(
        "/api/v1/dashboard/",
        json={"name": "Headers Bot", "description": "security header check"},
        headers=headers,
    )
    assert create_bot.status_code in (200, 201)
    assert create_bot.headers.get("x-content-type-options") == "nosniff"
    assert create_bot.headers.get("x-frame-options") == "DENY"

