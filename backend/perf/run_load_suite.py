#!/usr/bin/env python3
import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return float(ordered[idx])


def summarize(name: str, latencies_ms: list[float], total_s: float, failures: int) -> dict[str, Any]:
    count = len(latencies_ms)
    return {
        "operation": name,
        "requests": count,
        "failures": failures,
        "total_seconds": round(total_s, 4),
        "throughput_rps": round((count / total_s) if total_s > 0 else 0.0, 2),
        "latency_ms": {
            "avg": round(statistics.mean(latencies_ms), 2) if latencies_ms else 0.0,
            "p50": round(percentile(latencies_ms, 50), 2),
            "p95": round(percentile(latencies_ms, 95), 2),
            "p99": round(percentile(latencies_ms, 99), 2),
            "max": round(max(latencies_ms), 2) if latencies_ms else 0.0,
        },
    }


@dataclass
class Scenario:
    name: str
    method: str
    path: str
    requests: int
    concurrency: int
    json_body_factory: Callable[[int], dict[str, Any]] | None = None
    expected_statuses: tuple[int, ...] = (200,)


async def login(base_url: str, username: str, password: str) -> str:
    async with httpx.AsyncClient(base_url=base_url, timeout=20.0) as client:
        resp = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
        resp.raise_for_status()
        return resp.json()["access_token"]


async def create_bot(base_url: str, token: str, name: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=base_url, timeout=20.0) as client:
        resp = await client.post(
            "/api/v1/dashboard/",
            headers=headers,
            json={
                "name": name,
                "description": "load suite bot",
                "prompt_template": "You are concise",
                "welcome_message": "Hi",
                "primary_color": "#2563eb",
            },
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def run_scenario(base_url: str, token: str, scenario: Scenario) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    sem = asyncio.Semaphore(scenario.concurrency)
    latencies_ms: list[float] = []
    failures = 0

    async with httpx.AsyncClient(base_url=base_url, timeout=45.0) as client:
        async def one(idx: int):
            nonlocal failures
            async with sem:
                payload = scenario.json_body_factory(idx) if scenario.json_body_factory else None
                start = time.perf_counter()
                try:
                    resp = await client.request(scenario.method, scenario.path, headers=headers, json=payload)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    if resp.status_code not in scenario.expected_statuses:
                        failures += 1
                        return
                    latencies_ms.append(elapsed_ms)
                except Exception:
                    failures += 1

        started = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(scenario.requests)))
        total_s = time.perf_counter() - started

    return summarize(scenario.name, latencies_ms, total_s, failures)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run load tests against live TangentCloud endpoints.")
    parser.add_argument("--base-url", default="http://localhost:9100")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--chat-requests", type=int, default=50)
    parser.add_argument("--chat-concurrency", type=int, default=10)
    parser.add_argument("--conversations-requests", type=int, default=50)
    parser.add_argument("--conversations-concurrency", type=int, default=10)
    parser.add_argument("--scrape-requests", type=int, default=5)
    parser.add_argument("--scrape-concurrency", type=int, default=2)
    parser.add_argument("--scrape-url", default="https://example.com")
    return parser.parse_args()


async def main():
    args = parse_args()
    token = await login(args.base_url, args.username, args.password)
    bot_id = await create_bot(args.base_url, token, f"Perf Bot {int(time.time())}")

    scenarios = [
        Scenario(
            name="chat_public_style",
            method="POST",
            path="/api/v1/chat/public",
            requests=args.chat_requests,
            concurrency=args.chat_concurrency,
            json_body_factory=lambda i: {"bot_id": bot_id, "message": f"Load test message {i}"},
        ),
        Scenario(
            name="dashboard_conversations",
            method="GET",
            path="/api/v1/dashboard/conversations",
            requests=args.conversations_requests,
            concurrency=args.conversations_concurrency,
            json_body_factory=None,
        ),
        Scenario(
            name="ingest_scrape",
            method="POST",
            path="/api/v1/ingest/scrape",
            requests=args.scrape_requests,
            concurrency=args.scrape_concurrency,
            json_body_factory=lambda i: {
                "url": args.scrape_url,
                "max_pages": 1,
                "use_sitemaps": False,
                "index_sections": False,
            },
            expected_statuses=(200, 400, 403),
        ),
    ]

    results = {}
    for scenario in scenarios:
        results[scenario.name] = await run_scenario(args.base_url, token, scenario)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "results": results,
    }

    out_dir = Path(__file__).resolve().parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"load_suite_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
