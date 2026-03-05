from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ModuleDefinition:
    slug: str
    display_name: str
    owns: Tuple[str, ...]
    depends_on: Tuple[str, ...]


MODULES: Tuple[ModuleDefinition, ...] = (
    ModuleDefinition("identity", "Identity", ("auth", "users", "api-keys"), ("shared_kernel",)),
    ModuleDefinition("tenant", "Tenant", ("tenant-profile", "plan", "feature-flags", "limits"), ("shared_kernel", "identity")),
    ModuleDefinition("bot_management", "Bot Management", ("bots", "flows", "faqs", "quick-replies"), ("shared_kernel", "tenant")),
    ModuleDefinition("chat", "Chat", ("conversations", "messages", "handoff-state"), ("shared_kernel", "tenant", "bot_management", "identity")),
    ModuleDefinition("ai_orchestration", "AI Orchestration", ("prompt-assembly", "provider-routing", "fallback-policy"), ("shared_kernel", "tenant", "bot_management")),
    ModuleDefinition("knowledge_ingestion", "Knowledge Ingestion", ("uploads", "crawl", "chunking", "document-lifecycle"), ("shared_kernel", "tenant")),
    ModuleDefinition("knowledge_retrieval", "Knowledge Retrieval", ("vector-search", "reranking", "source-attribution"), ("shared_kernel", "tenant")),
    ModuleDefinition("lead_management", "Lead Management", ("lead-forms", "submissions"), ("shared_kernel", "tenant", "bot_management", "chat")),
    ModuleDefinition("analytics", "Analytics", ("dashboards", "exports", "reporting"), ("shared_kernel", "tenant")),
    ModuleDefinition("billing", "Billing", ("plans", "quota", "subscriptions", "usage-ledger"), ("shared_kernel", "tenant")),
    ModuleDefinition("integrations", "Integrations", ("slack", "webhooks", "crm-adapters"), ("shared_kernel", "tenant")),
    ModuleDefinition("notifications", "Notifications", ("email", "webhooks", "alerts"), ("shared_kernel", "tenant", "integrations")),
    ModuleDefinition("audit_compliance", "Audit and Compliance", ("audit-trail", "consent", "retention"), ("shared_kernel", "identity", "tenant")),
    ModuleDefinition("admin_platform", "Admin Platform", ("ops-tools", "support-actions"), ("shared_kernel", "identity", "tenant", "analytics", "billing")),
)
