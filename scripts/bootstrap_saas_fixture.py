#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
TESTDATA_DIR = REPO_ROOT / "docs" / "testdata"
CLIENTS_PATH = TESTDATA_DIR / "saas_clients.json"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.core.database import SessionLocal, TenantDB, TenantUsageDB, DocumentDB  # noqa: E402
from app.models.bot import Bot  # noqa: E402


BASE_URL = os.environ.get("SAAS_VALIDATION_BASE_URL", "http://127.0.0.1:9100")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "password123")


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


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _synthetic_profile(client: ClientConfig) -> str:
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


def _pricing_profile(client: ClientConfig) -> str:
    return (
        f"{client.tenant_name} pricing plans: Starter plan starts at $49 per month for one bot and 2,000 messages. "
        "Pro plan is $149 per month for up to 5 bots and 20,000 messages. "
        "Enterprise pricing is custom with SSO, dedicated support, and advanced compliance controls."
    )


def _upsert_tenant_and_bot(client: ClientConfig) -> int:
    db = SessionLocal()
    try:
        tenant = db.query(TenantDB).filter(TenantDB.id == client.tenant_id).first()
        if not tenant:
            tenant = TenantDB(id=client.tenant_id, name=client.tenant_name, plan=client.plan, is_active=True)
            db.add(tenant)
        else:
            tenant.name = client.tenant_name
            tenant.plan = client.plan
            tenant.is_active = True

        usage = db.query(TenantUsageDB).filter(TenantUsageDB.tenant_id == client.tenant_id).first()
        if not usage:
            usage = TenantUsageDB(tenant_id=client.tenant_id, messages_sent=0, documents_indexed=0)
            db.add(usage)
        else:
            usage.messages_sent = 0
            usage.documents_indexed = 0

        bot = db.query(Bot).filter(Bot.tenant_id == client.tenant_id, Bot.name == client.bot_name).first()
        if not bot:
            bot = Bot(
                tenant_id=client.tenant_id,
                name=client.bot_name,
                description=f"{client.tenant_name} support assistant",
                prompt_template="You are a calm, helpful customer support assistant.",
                welcome_message="Welcome to TangentCloud. Ask me anything.",
                is_active=True,
            )
            db.add(bot)
            db.flush()
        else:
            bot.is_active = True

        db.commit()
        return bot.id
    finally:
        db.close()


def _auth_headers(tenant_id: str) -> dict[str, str]:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"username": tenant_id, "password": AUTH_PASSWORD},
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _clear_existing_docs(headers: dict[str, str], tenant_id: str) -> None:
    response = requests.get(f"{BASE_URL}/api/v1/ingest/", headers=headers, timeout=30)
    response.raise_for_status()
    for doc in response.json():
        delete_resp = requests.delete(f"{BASE_URL}/api/v1/ingest/{doc['id']}", headers=headers, timeout=30)
        if delete_resp.status_code < 400:
            continue
        # Recovery path for drift between SQL rows and vector store state.
        db = SessionLocal()
        try:
            row = db.query(DocumentDB).filter(DocumentDB.id == doc["id"], DocumentDB.tenant_id == tenant_id).first()
            if row:
                db.delete(row)
                db.commit()
        finally:
            db.close()

    db = SessionLocal()
    try:
        usage = db.query(TenantUsageDB).filter(TenantUsageDB.tenant_id == tenant_id).first()
        if usage:
            usage.documents_indexed = 0
            usage.messages_sent = 0
            db.commit()
    finally:
        db.close()


def _ingest_text(headers: dict[str, str], title: str, source: str, text: str) -> None:
    response = requests.post(
        f"{BASE_URL}/api/v1/ingest/",
        headers=headers,
        json={"text": text, "metadata": {"title": title, "source": source}},
        timeout=60,
    )
    response.raise_for_status()


def _fetch_soup(url: str) -> BeautifulSoup:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _bootstrap_client(client: ClientConfig) -> dict:
    bot_id = _upsert_tenant_and_bot(client)
    headers = _auth_headers(client.tenant_id)
    _clear_existing_docs(headers, client.tenant_id)

    _ingest_text(
        headers,
        f"{client.tenant_name} Synthetic Profile",
        f"synthetic://{client.expected_keyword}/profile",
        _synthetic_profile(client),
    )
    _ingest_text(
        headers,
        "Pricing Plans",
        f"synthetic://{client.expected_keyword}/pricing",
        _pricing_profile(client),
    )

    soup = _fetch_soup(client.website)
    page_title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else client.tenant_name)
    page_text = _clean_text(soup.get_text(" ", strip=True))
    if page_text:
        _ingest_text(headers, page_title, client.website, page_text)

    anchored = []
    for anchor_id in client.anchor_ids:
        node = soup.find(id=anchor_id)
        if not node:
            continue
        section_text = _clean_text(node.get_text(" ", strip=True))
        if len(section_text) < 40:
            continue
        source = f"{client.website.rstrip('/')}/#{anchor_id}" if "#" not in client.website else client.website
        _ingest_text(
            headers,
            f"{client.tenant_name} {anchor_id.title()} Section",
            source,
            section_text,
        )
        anchored.append(anchor_id)

    return {
        "tenant_id": client.tenant_id,
        "tenant_name": client.tenant_name,
        "bot_id": bot_id,
        "website": client.website,
        "anchored_sections": anchored,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="all", help="tenant id, tenant name, or 'all'")
    args = parser.parse_args()

    results = [_bootstrap_client(client) for client in _selected_clients(args.tenant)]
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
