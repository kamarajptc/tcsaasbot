import json
from pathlib import Path


def test_grafana_dashboard_has_error_latency_and_business_panels():
    repo_root = Path(__file__).resolve().parents[2]
    dashboard_path = repo_root / "monitoring" / "grafana" / "dashboards" / "tangentcloud-monitoring.json"
    payload = json.loads(dashboard_path.read_text())

    titles = [panel.get("title", "") for panel in payload.get("panels", [])]
    assert "⚠️ Errors (4xx + 5xx)" in titles
    assert "Request Duration (ms)" in titles
    assert "Leads Submitted" in titles

    request_error_panel = next(p for p in payload["panels"] if p.get("title") == "⚠️ Errors (4xx + 5xx)")
    assert "status_code >= 400" in request_error_panel["targets"][0]["expr"]
