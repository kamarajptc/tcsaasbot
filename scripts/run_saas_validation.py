#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "docs" / "reports"
TESTDATA_DIR = REPO_ROOT / "docs" / "testdata"
CLIENTS_PATH = TESTDATA_DIR / "saas_clients.json"
BASE_URL = "http://127.0.0.1:9100"
AUDIT_URL = "http://127.0.0.1:9100/api/v1/ingest/audit/test-runner"
LOGIN_URL = "http://127.0.0.1:9100/api/v1/auth/login"
BOT_LIST_URL = "http://127.0.0.1:9100/api/v1/dashboard/"
AUTH_PASSWORD = "password123"
_TOKEN_CACHE: dict[str, dict[str, str]] = {}


@dataclass(frozen=True)
class ClientConfig:
    tenant_id: str
    tenant_name: str
    plan: str
    website: str
    bot_name: str
    category: str
    expected_keyword: str
    anchor_ids: tuple[str, ...] = ()
    golden_set: str | None = None


@dataclass(frozen=True)
class ValidationCase:
    case_id: str
    scenario: str
    category: str
    question: str
    expected_contains: tuple[str, ...]
    forbidden_contains: tuple[str, ...]
    notes: str = ""


def _load_clients() -> list[ClientConfig]:
    payload = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
    return [
        ClientConfig(
            tenant_id=item["tenant_id"],
            tenant_name=item["tenant_name"],
            plan=item["plan"],
            website=item["website"],
            bot_name=item["bot_name"],
            category=item["category"],
            expected_keyword=item["expected_keyword"],
            anchor_ids=tuple(item.get("anchor_ids") or ()),
            golden_set=item.get("golden_set"),
        )
        for item in payload
    ]


def _selected_clients(selector: str) -> list[ClientConfig]:
    clients = _load_clients()
    if selector == "all":
        return clients
    selected = [
        client for client in clients
        if client.tenant_id == selector or client.tenant_name.lower() == selector.lower()
    ]
    if not selected:
        raise SystemExit(f"Unknown tenant selector: {selector}")
    return selected


def _generic_cases(client: ClientConfig) -> tuple[ValidationCase, ...]:
    canonical = client.tenant_name.lower().replace(" ", "-")
    website_domain = client.website.replace("https://", "").replace("http://", "").strip("/")
    cases = [
        ValidationCase("GEN-001", "positive", "validation", f"What is the validation code for {client.tenant_name}?", (f"vc-{canonical}-2026",), ()),
        ValidationCase("GEN-002", "positive", "validation", f"What support alias is configured for {client.tenant_name}?", (f"support-{canonical}",), ()),
        ValidationCase("GEN-003", "positive", "validation", f"What is the test marker for {client.tenant_name}?", (f"qa-ready-{canonical}",), ()),
        ValidationCase("GEN-004", "positive", "validation", f"What is the official website for {client.tenant_name}?", (website_domain,), ()),
        ValidationCase("GEN-005", "positive", "validation", f"Which business category is assigned to {client.tenant_name}?", (client.category.split()[0].lower(),), ()),
        ValidationCase("GEN-006", "positive", "validation", f"Tell me the brand keyword of {client.tenant_name}.", (client.expected_keyword.lower(),), ()),
        ValidationCase("GEN-007", "positive", "validation", f"Repeat the validation code for {client.tenant_name}.", (f"vc-{canonical}-2026",), ()),
        ValidationCase("GEN-008", "positive", "validation", f"Repeat the support alias for {client.tenant_name}.", (f"support-{canonical}",), ()),
        ValidationCase("GEN-009", "positive", "validation", f"Repeat the test marker for {client.tenant_name}.", (f"qa-ready-{canonical}",), ()),
        ValidationCase("GEN-010", "positive", "validation", f"Which domain is the primary knowledge domain for {client.tenant_name}?", (website_domain,), ()),
        ValidationCase("GEN-011", "positive", "profile", f"Give a short profile summary for {client.tenant_name}.", (client.expected_keyword.lower(),), ("knowledge ledger",)),
    ]
    return tuple(cases)


def _load_cases(client: ClientConfig) -> tuple[ValidationCase, ...]:
    if client.golden_set:
        path = TESTDATA_DIR / client.golden_set
        payload = json.loads(path.read_text(encoding="utf-8"))
        return tuple(
            ValidationCase(
                case_id=item["case_id"],
                scenario=item["scenario"],
                category=item["category"],
                question=item["question"],
                expected_contains=tuple(item.get("expected_contains") or ()),
                forbidden_contains=tuple(item.get("forbidden_contains") or ()),
                notes=item.get("notes", ""),
            )
            for item in payload
        )
    return _generic_cases(client)


def _login_headers(tenant_id: str) -> dict[str, str]:
    cached = _TOKEN_CACHE.get(tenant_id)
    if cached:
        return cached

    last_error = None
    with httpx.Client(timeout=30.0) as client:
        for attempt in range(6):
            response = client.post(LOGIN_URL, json={"username": tenant_id, "password": AUTH_PASSWORD})
            if response.status_code == 429:
                retry_after_raw = response.headers.get("Retry-After", "1")
                try:
                    retry_after = max(1.0, float(retry_after_raw))
                except ValueError:
                    retry_after = 1.0
                time.sleep(min(10.0, retry_after + (attempt * 0.25) + random.uniform(0.0, 0.25)))
                last_error = httpx.HTTPStatusError(
                    f"Auth login throttled for tenant {tenant_id}",
                    request=response.request,
                    response=response,
                )
                continue
            response.raise_for_status()
            token = response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            _TOKEN_CACHE[tenant_id] = headers
            return headers

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unable to obtain auth token for {tenant_id}")


def _passes(case: ValidationCase, answer: str, status_code: int) -> tuple[bool, str]:
    lowered = (answer or "").lower()
    missing = [token for token in case.expected_contains if token.lower() not in lowered]
    forbidden = [token for token in case.forbidden_contains if token.lower() in lowered]
    notes = []
    if status_code != 200:
        notes.append(f"http_status={status_code}")
    if missing:
        notes.append(f"missing={missing}")
    if forbidden:
        notes.append(f"forbidden={forbidden}")
    return not notes, "; ".join(notes)


def _resolve_bot_id(tenant_id: str, bot_name: str, headers: dict[str, str]) -> int:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(BOT_LIST_URL, headers=headers)
        response.raise_for_status()
        bots = response.json()

    if not isinstance(bots, list):
        raise RuntimeError(f"Unexpected bot list payload for {tenant_id}: {bots!r}")

    normalized_name = bot_name.strip().lower()
    active_bots = [bot for bot in bots if bot.get("is_active") is not False]
    for bot in active_bots:
        if str(bot.get("name", "")).strip().lower() == normalized_name:
            return int(bot["id"])
    if active_bots:
        return int(active_bots[0]["id"])
    raise RuntimeError(f"No active bot found for {tenant_id}")


def run_client_cases(client_cfg: ClientConfig) -> list[dict]:
    headers = _login_headers(client_cfg.tenant_id)
    bot_id = _resolve_bot_id(client_cfg.tenant_id, client_cfg.bot_name, headers)
    rows: list[dict] = []
    cases = _load_cases(client_cfg)

    with httpx.Client(timeout=30.0) as client:
        for case in cases:
            started = time.perf_counter()
            response = client.post(AUDIT_URL, headers=headers, json={"bot_id": bot_id, "question": case.question})
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            payload = response.json()
            answer = payload.get("answer", "")
            sources = payload.get("sources") or []
            passed, notes = _passes(case, answer, response.status_code)
            rows.append(
                {
                    "run_at_utc": datetime.now(timezone.utc).isoformat(),
                    "tenant_id": client_cfg.tenant_id,
                    "tenant_name": client_cfg.tenant_name,
                    "bot_id": bot_id,
                    "case_id": case.case_id,
                    "scenario": case.scenario,
                    "category": case.category,
                    "question": case.question,
                    "expected_contains": " | ".join(case.expected_contains),
                    "forbidden_contains": " | ".join(case.forbidden_contains),
                    "http_status": response.status_code,
                    "passed": passed,
                    "latency_ms": elapsed_ms,
                    "source_count": len(sources),
                    "answer": answer,
                    "evaluation_notes": notes or case.notes,
                }
            )
            time.sleep(0.05)
    return rows


def _write_outputs(rows: list[dict], slug: str) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = REPORTS_DIR / f"saas_validation_{slug}.csv"
    summary_path = REPORTS_DIR / f"saas_validation_{slug}.json"
    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    by_tenant: dict[str, dict[str, int]] = {}
    for tenant_id in sorted({row["tenant_id"] for row in rows}):
        tenant_rows = [row for row in rows if row["tenant_id"] == tenant_id]
        by_tenant[tenant_id] = {
            "total": len(tenant_rows),
            "passed": sum(1 for row in tenant_rows if row["passed"]),
            "failed": sum(1 for row in tenant_rows if not row["passed"]),
        }

    summary = {
        "total": len(rows),
        "passed": sum(1 for row in rows if row["passed"]),
        "failed": sum(1 for row in rows if not row["passed"]),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "by_tenant": by_tenant,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return csv_path, summary_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="all", help="tenant id, tenant name, or 'all'")
    args = parser.parse_args()

    clients = _selected_clients(args.tenant)
    rows: list[dict] = []
    for client in clients:
        rows.extend(run_client_cases(client))

    slug = "all" if args.tenant == "all" else args.tenant.lower().replace("@", "_at_").replace(".", "_")
    csv_path, summary_path = _write_outputs(rows, slug)
    print(csv_path)
    print(summary_path)
    print(json.dumps({"total": len(rows), "passed": sum(1 for row in rows if row["passed"]), "failed": sum(1 for row in rows if not row["passed"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
