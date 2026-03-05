#!/usr/bin/env python3
import argparse
import json
import logging
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock


def _prepare_imports():
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = repo_root / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    os.environ.setdefault("GOOGLE_API_KEY", "dummy_key")
    os.environ.setdefault("OPENAI_API_KEY", "dummy_key")
    os.environ.setdefault("LLM_PROVIDER", "gemini")
    os.environ.setdefault("ALLOW_API_KEY_AUTH", "false")
    os.environ.setdefault("AUTH_PASSWORD", "password123")
    os.environ.setdefault("AUTH_REQUIRE_EXISTING_TENANT", "true")

    sys.modules["app.core.telemetry"] = MagicMock()
    logging.getLogger("TangentCloud").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def summarize(name: str, latencies_ms: List[float], total_s: float) -> Dict[str, Any]:
    count = len(latencies_ms)
    return {
        "operation": name,
        "requests": count,
        "total_seconds": round(total_s, 4),
        "throughput_rps": round((count / total_s) if total_s > 0 else 0.0, 2),
        "latency_ms": {
            "avg": round(statistics.mean(latencies_ms), 2) if latencies_ms else 0.0,
            "p50": round(percentile(latencies_ms, 0.50), 2),
            "p95": round(percentile(latencies_ms, 0.95), 2),
            "p99": round(percentile(latencies_ms, 0.99), 2),
            "max": round(max(latencies_ms), 2) if latencies_ms else 0.0,
        },
    }


def _worker_post(client, path: str, headers: Dict[str, str], payload: Dict[str, Any]) -> float:
    start = time.perf_counter()
    resp = client.post(path, json=payload, headers=headers)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if resp.status_code != 200:
        raise RuntimeError(f"Request failed ({resp.status_code}): {path} -> {resp.text}")
    return elapsed_ms


def run(args: argparse.Namespace) -> Dict[str, Any]:
    _prepare_imports()

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.main import app
    from app.core.database import Base, TenantDB, get_db
    from app.core.security import create_access_token
    from app.services.rag_service import rag_service

    def fake_query(message, collection_name="default", chat_history=None, bot_instructions="", bot_name=None):
        return {
            "answer": f"Synthetic answer for: {message[:32]}",
            "sources": [{"title": "synthetic", "score": 0.99}],
        }

    def fake_ingest_text(text, metadata=None, collection_name="default"):
        return {"chunks_added": 1, "status": "ok"}

    rag_service.query = fake_query
    rag_service.ingest_text = fake_ingest_text

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    tenant_id = "perf_tenant@example.com"
    tenant = TenantDB(id=tenant_id, name="Perf Tenant", plan="enterprise", is_active=True)
    session.add(tenant)
    session.commit()

    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id})
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        bot_resp = client.post(
            "/api/v1/dashboard/",
            json={
                "name": "Perf Bot",
                "description": "load baseline bot",
                "prompt_template": "You are concise",
                "welcome_message": "Hi",
                "primary_color": "#2563eb",
            },
            headers=headers,
        )
        if bot_resp.status_code != 200:
            raise RuntimeError(f"Failed to create bot: {bot_resp.status_code} {bot_resp.text}")
        bot_id = bot_resp.json()["id"]

        warmup_chat = {"message": "warmup", "bot_id": bot_id}
        warmup_ingest = {"text": "warmup text", "metadata": {"title": "warmup", "source": "perf"}}
        for _ in range(args.warmup):
            client.post("/api/v1/chat/", json=warmup_chat, headers=headers)
            client.post("/api/v1/ingest/", json=warmup_ingest, headers=headers)

        chat_payload = {"message": "Need help with onboarding and billing", "bot_id": bot_id}
        ingest_payload = {
            "text": "Synthetic knowledge payload for ingestion baseline.",
            "metadata": {"title": "PerfDoc", "source": "perf"},
        }

        chat_latencies: List[float] = []
        ingest_latencies: List[float] = []

        chat_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.chat_workers) as pool:
            futures = [
                pool.submit(_worker_post, client, "/api/v1/chat/", headers, chat_payload)
                for _ in range(args.chat_requests)
            ]
            for fut in as_completed(futures):
                chat_latencies.append(fut.result())
        chat_total = time.perf_counter() - chat_start

        ingest_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.ingest_workers) as pool:
            futures = [
                pool.submit(_worker_post, client, "/api/v1/ingest/", headers, ingest_payload)
                for _ in range(args.ingest_requests)
            ]
            for fut in as_completed(futures):
                ingest_latencies.append(fut.result())
        ingest_total = time.perf_counter() - ingest_start

    app.dependency_overrides.clear()
    session.close()

    chat_summary = summarize("chat", chat_latencies, chat_total)
    ingest_summary = summarize("ingest", ingest_latencies, ingest_total)

    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": generated_at,
        "environment": {
            "runner": "fastapi-testclient",
            "database": "sqlite-memory",
            "chat_workers": args.chat_workers,
            "ingest_workers": args.ingest_workers,
            "chat_requests": args.chat_requests,
            "ingest_requests": args.ingest_requests,
            "warmup": args.warmup,
        },
        "results": {
            "chat": chat_summary,
            "ingest": ingest_summary,
        },
        "recommendations": [
            "Move sqlite to managed Postgres for write-heavy ingest workloads.",
            "Add worker queue for crawl/ingest to isolate user-facing API latency.",
            "Cache frequent chat retrieval paths and keep vector index warm.",
            "Add p95 latency SLO alerts and request-rate autoscaling policy.",
        ],
    }
    return report


def write_report(report: Dict[str, Any], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"baseline_{stamp}.json"
    md_path = output_dir / "LOAD_TEST_REPORT.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    chat = report["results"]["chat"]
    ingest = report["results"]["ingest"]

    md = f"""# Performance Baseline Report

Generated at (UTC): {report['generated_at']}

## Scope
- Runner: {report['environment']['runner']}
- Chat requests: {report['environment']['chat_requests']} (workers={report['environment']['chat_workers']})
- Ingest requests: {report['environment']['ingest_requests']} (workers={report['environment']['ingest_workers']})
- Warmup iterations: {report['environment']['warmup']}

## Results

### Chat (`POST /api/v1/chat/`)
- Throughput: {chat['throughput_rps']} req/s
- Avg latency: {chat['latency_ms']['avg']} ms
- P50 latency: {chat['latency_ms']['p50']} ms
- P95 latency: {chat['latency_ms']['p95']} ms
- P99 latency: {chat['latency_ms']['p99']} ms
- Max latency: {chat['latency_ms']['max']} ms

### Ingest (`POST /api/v1/ingest/`)
- Throughput: {ingest['throughput_rps']} req/s
- Avg latency: {ingest['latency_ms']['avg']} ms
- P50 latency: {ingest['latency_ms']['p50']} ms
- P95 latency: {ingest['latency_ms']['p95']} ms
- P99 latency: {ingest['latency_ms']['p99']} ms
- Max latency: {ingest['latency_ms']['max']} ms

## Tuning Recommendations
"""
    for item in report["recommendations"]:
        md += f"- {item}\n"

    md += f"\n## Raw Artifact\n- JSON: `{json_path}`\n"
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run chat/ingest baseline load test")
    parser.add_argument("--chat-requests", type=int, default=200)
    parser.add_argument("--ingest-requests", type=int, default=120)
    parser.add_argument("--chat-workers", type=int, default=10)
    parser.add_argument("--ingest-workers", type=int, default=6)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "reports")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = run(args)
    json_path, md_path = write_report(report, args.output_dir)
    print(f"Wrote JSON report: {json_path}")
    print(f"Wrote markdown report: {md_path}")
