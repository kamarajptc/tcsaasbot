#!/usr/bin/env python3
"""
Reset SaaS data, crawl 5 client websites, and generate synthetic Q/A validation.

Outputs:
- docs/reports/multiclient_seed_report.json
- docs/reports/multiclient_qna_results.csv
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import argparse
import shutil
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
# Ensure backend/.env is discovered by pydantic Settings env_file=".env".
os.chdir(BACKEND_ROOT)

# Ensure local/test-safe auth behavior for the script runtime.
os.environ.setdefault("ALLOW_API_KEY_AUTH", "false")
os.environ.setdefault("AUTH_REQUIRE_EXISTING_TENANT", "false")
sys.modules["app.core.telemetry"] = MagicMock()

from app.main import app  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.core.database import (  # noqa: E402
    Base,
    engine,
    SessionLocal,
    TenantDB,
    TenantUsageDB,
)
from app.services.rag_service import rag_service  # noqa: E402


class LocalHashEmbeddings:
    """Offline deterministic embeddings for local synthetic seeding."""

    def __init__(self, dims: int = 96):
        self.dims = dims

    def _vector(self, text: str) -> List[float]:
        text = text or ""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for i in range(self.dims):
            b = digest[i % len(digest)]
            values.append((b / 255.0) * 2.0 - 1.0)
        return values

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._vector(text)


@dataclass
class ClientConfig:
    tenant_id: str
    tenant_name: str
    plan: str
    website: str
    bot_name: str
    category: str
    expected_keyword: str


CLIENTS: List[ClientConfig] = [
    ClientConfig(
        tenant_id="ops@tangentcloud.in",
        tenant_name="TangentCloud",
        plan="enterprise",
        website="https://www.tangentcloud.in/",
        bot_name="TangentCloud Assistant",
        category="AI SaaS Platforms",
        expected_keyword="tangentcloud",
    ),
    ClientConfig(
        tenant_id="ops@dataflo.io",
        tenant_name="dataflo",
        plan="pro",
        website="https://www.dataflo.io/",
        bot_name="Dataflo Workflow Guide",
        category="No-Code Data Automation",
        expected_keyword="dataflo",
    ),
    ClientConfig(
        tenant_id="ops@adamsbridge.com",
        tenant_name="Adamsbridge",
        plan="enterprise",
        website="https://adamsbridge.com/",
        bot_name="Adamsbridge IAM Assistant",
        category="Identity and Access Management",
        expected_keyword="adamsbridge",
    ),
    ClientConfig(
        tenant_id="ops@workez.in",
        tenant_name="WorkEZ",
        plan="pro",
        website="https://workez.in/",
        bot_name="WorkEZ HR Assistant",
        category="HRMS and Payroll",
        expected_keyword="workez",
    ),
]


def _headers(tenant_id: str) -> Dict[str, str]:
    token = create_access_token({"sub": tenant_id, "tenant_id": tenant_id, "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


def _reset_sql() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _reset_vectors() -> List[str]:
    removed = []
    candidates = [
        REPO_ROOT / "qdrant_db",
        BACKEND_ROOT / "qdrant_db",
    ]
    for c in candidates:
        if c.exists():
            shutil.rmtree(c, ignore_errors=True)
            removed.append(str(c))
    # Ensure default path exists again
    (REPO_ROOT / "qdrant_db").mkdir(parents=True, exist_ok=True)
    rag_service.persist_directory = str(REPO_ROOT / "qdrant_db")
    rag_service._client = QdrantClient(path=rag_service.persist_directory)
    return removed


def _ensure_tenant(tenant_id: str, tenant_name: str, plan: str) -> None:
    db = SessionLocal()
    try:
        tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
        if not tenant:
            tenant = TenantDB(id=tenant_id, name=tenant_name, plan=plan, is_active=True)
            db.add(tenant)
        else:
            tenant.name = tenant_name
            tenant.plan = plan
            tenant.is_active = True

        usage = db.query(TenantUsageDB).filter(TenantUsageDB.tenant_id == tenant_id).first()
        if not usage:
            db.add(TenantUsageDB(tenant_id=tenant_id, messages_sent=0, documents_indexed=0))
        db.commit()
    finally:
        db.close()


def _synthetic_knowledge(client: ClientConfig) -> str:
    canonical = client.tenant_name.lower().replace(" ", "-")
    return (
        f"{client.tenant_name} company profile.\n"
        f"Official website: {client.website}\n"
        f"Business category: {client.category}\n"
        f"Brand keyword: {client.expected_keyword}\n"
        f"Validation code: vc-{canonical}-2026\n"
        f"Support alias: support-{canonical}\n"
        f"Primary knowledge domain: {client.website}\n"
        f"Test marker: qa-ready-{canonical}\n"
        f"Support contacts are available in website contact pages.\n"
        f"Knowledge policy: respond using indexed website pages and cite concise answers.\n"
    )


def _questions(client: ClientConfig) -> List[Dict[str, str]]:
    canonical = client.tenant_name.lower().replace(" ", "-")
    validation_code = f"vc-{canonical}-2026"
    support_alias = f"support-{canonical}"
    test_marker = f"qa-ready-{canonical}"
    return [
        {
            "question": f"What is the validation code for {client.tenant_name}?",
            "expected_keyword": validation_code,
        },
        {
            "question": f"What support alias is configured for {client.tenant_name}?",
            "expected_keyword": support_alias,
        },
        {
            "question": f"What is the test marker for {client.tenant_name}?",
            "expected_keyword": test_marker,
        },
        {
            "question": f"What is the official website for {client.tenant_name}?",
            "expected_keyword": client.website.replace("https://", "").strip("/"),
        },
        {
            "question": f"Which business category is assigned to {client.tenant_name}?",
            "expected_keyword": client.category.split()[0].lower(),
        },
        {
            "question": f"Tell me the brand keyword of {client.tenant_name}.",
            "expected_keyword": client.expected_keyword,
        },
        {
            "question": f"Repeat the validation code for {client.tenant_name}.",
            "expected_keyword": validation_code,
        },
        {
            "question": f"Repeat the support alias for {client.tenant_name}.",
            "expected_keyword": support_alias,
        },
        {
            "question": f"Repeat the test marker for {client.tenant_name}.",
            "expected_keyword": test_marker,
        },
        {
            "question": f"Which domain is the primary knowledge domain for {client.tenant_name}?",
            "expected_keyword": client.website.replace("https://", "").strip("/"),
        },
        {
            "question": f"Give a short profile summary for {client.tenant_name}.",
            "expected_keyword": client.expected_keyword,
        },
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset and reseed multi-tenant SaaS demo data")
    parser.add_argument(
        "--embedding-mode",
        choices=["runtime", "local"],
        default="runtime",
        help="Use runtime provider embeddings (default) or local deterministic embeddings.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.embedding_mode == "local":
        rag_service.embeddings = LocalHashEmbeddings()
    warnings.filterwarnings("ignore", message="Relevance scores must be between 0 and 1")

    _reset_sql()
    removed_vector_paths = _reset_vectors()

    now = datetime.now(timezone.utc).isoformat()
    report: Dict[str, object] = {
        "generated_at": now,
        "reset": {
            "sql_reset": True,
            "vector_paths_removed": removed_vector_paths,
            "embedding_mode": args.embedding_mode,
        },
        "clients": [],
    }
    qna_rows: List[Dict[str, object]] = []

    with TestClient(app) as client:
        for cfg in CLIENTS:
            _ensure_tenant(cfg.tenant_id, cfg.tenant_name, cfg.plan)
            headers = _headers(cfg.tenant_id)

            bot_resp = client.post(
                "/api/v1/dashboard/",
                json={
                    "name": cfg.bot_name,
                    "description": f"{cfg.category} assistant for {cfg.tenant_name}",
                    "prompt_template": (
                        f"You are {cfg.bot_name}. Provide clear and concise responses for "
                        f"{cfg.tenant_name} in the category {cfg.category}."
                    ),
                    "welcome_message": f"Welcome to {cfg.tenant_name}. Ask me anything.",
                    "is_active": True,
                },
                headers=headers,
            )
            if bot_resp.status_code not in (200, 201):
                raise RuntimeError(f"Bot creation failed for {cfg.tenant_id}: {bot_resp.status_code} {bot_resp.text}")
            bot_id = bot_resp.json()["id"]

            scrape_resp = client.post(
                "/api/v1/ingest/scrape",
                json={
                    "url": cfg.website,
                    "max_pages": 12,
                    "use_sitemaps": True,
                    "index_sections": True,
                },
                headers=headers,
            )
            scrape_ok = scrape_resp.status_code == 200
            scrape_data = scrape_resp.json() if scrape_ok else {"error": scrape_resp.text}

            synthetic_resp = client.post(
                "/api/v1/ingest/",
                json={
                    "text": _synthetic_knowledge(cfg),
                    "metadata": {
                        "title": f"{cfg.tenant_name} Synthetic Profile",
                        "source": f"synthetic://{cfg.tenant_name.lower().replace(' ', '_')}/profile",
                    },
                },
                headers=headers,
            )
            if synthetic_resp.status_code != 200:
                raise RuntimeError(f"Synthetic ingest failed for {cfg.tenant_id}: {synthetic_resp.status_code} {synthetic_resp.text}")

            docs_resp = client.get("/api/v1/ingest/", headers=headers)
            docs_count = len(docs_resp.json()) if docs_resp.status_code == 200 else 0

            client_qna_results = []
            for idx, q in enumerate(_questions(cfg), start=1):
                audit_resp = client.post(
                    "/api/v1/ingest/audit/test-runner",
                    json={
                        "bot_id": bot_id,
                        "question": q["question"],
                        "expected_keyword": q["expected_keyword"],
                    },
                    headers=headers,
                )
                if audit_resp.status_code != 200:
                    row = {
                        "tenant_id": cfg.tenant_id,
                        "tenant_name": cfg.tenant_name,
                        "bot_id": bot_id,
                        "question_no": idx,
                        "question": q["question"],
                        "expected_keyword": q["expected_keyword"],
                        "passed": False,
                        "response_ms": -1,
                        "answer": f"ERROR: {audit_resp.status_code}",
                    }
                else:
                    data = audit_resp.json()
                    row = {
                        "tenant_id": cfg.tenant_id,
                        "tenant_name": cfg.tenant_name,
                        "bot_id": bot_id,
                        "question_no": idx,
                        "question": q["question"],
                        "expected_keyword": q["expected_keyword"],
                        "passed": bool(data.get("passed")),
                        "response_ms": int(data.get("response_ms", 0)),
                        "answer": (data.get("answer") or "").replace("\n", " ").strip(),
                    }
                client_qna_results.append(row)
                qna_rows.append(row)

            passed_count = sum(1 for r in client_qna_results if r["passed"])
            report["clients"].append(
                {
                    "tenant_id": cfg.tenant_id,
                    "tenant_name": cfg.tenant_name,
                    "plan": cfg.plan,
                    "website": cfg.website,
                    "bot_id": bot_id,
                    "bot_name": cfg.bot_name,
                    "category": cfg.category,
                    "scrape_ok": scrape_ok,
                    "scrape_result": scrape_data,
                    "documents_count": docs_count,
                    "questions_total": len(client_qna_results),
                    "questions_passed": passed_count,
                    "questions_failed": len(client_qna_results) - passed_count,
                }
            )

    report_dir = REPO_ROOT / "docs" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "multiclient_seed_report.json"
    qna_csv_path = report_dir / "multiclient_qna_results.csv"

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    csv_fields = [
        "tenant_id",
        "tenant_name",
        "bot_id",
        "question_no",
        "question",
        "expected_keyword",
        "passed",
        "response_ms",
        "answer",
    ]
    with qna_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(qna_rows)

    total_questions = len(qna_rows)
    total_passed = sum(1 for r in qna_rows if r["passed"])
    print(f"Reset completed. Clients onboarded: {len(CLIENTS)}")
    print(f"Questions simulated: {total_questions}, passed: {total_passed}, failed: {total_questions - total_passed}")
    print(f"Report: {report_path}")
    print(f"QnA CSV: {qna_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
