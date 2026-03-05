from app.api.v1 import ingest as ingest_api
from app.core.security import create_access_token
from app.core.url_security import is_safe_outbound_url
from app.services.agent_service import calculator


def _headers(tenant_id: str):
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    return {"Authorization": f"Bearer {token}"}


def test_safe_calculator_blocks_code_execution():
    result = calculator.invoke("__import__('os').system('echo hacked')")
    assert "error evaluating expression" in result.lower()


def test_url_security_blocks_private_targets():
    assert is_safe_outbound_url("https://127.0.0.1/admin") is False
    assert is_safe_outbound_url("http://localhost:8000") is False


def test_scrape_blocks_unsafe_internal_url(client):
    resp = client.post(
        "/api/v1/ingest/scrape",
        json={"url": "http://127.0.0.1:8000", "use_sitemaps": False},
        headers=_headers("scrape_guard@example.com"),
    )
    assert resp.status_code == 400
    assert "unsafe scrape url" in resp.json()["detail"].lower()


def test_request_timing_and_rate_limit_headers_present(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "x-process-time-ms" in resp.headers
    assert "x-ratelimit-limit" in resp.headers
    assert "x-ratelimit-remaining" in resp.headers


def test_upload_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(ingest_api.settings, "MAX_UPLOAD_BYTES", 5)
    resp = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("big.txt", b"123456", "text/plain")},
        headers=_headers("upload_limit@example.com"),
    )
    assert resp.status_code == 413

