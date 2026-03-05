from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.database import TenantDB, TenantUsageDB


PLAN_LIMITS = {
    "starter": {"messages": 100, "documents": 5},
    "pro": {"messages": 5000, "documents": 50},
    "enterprise": {"messages": 100000, "documents": 1000},
}


def _tenant_plan(db: Session, tenant_id: str) -> str:
    tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
    return (tenant.plan if tenant and tenant.plan else "starter").lower()


def _usage_row(db: Session, tenant_id: str) -> TenantUsageDB:
    usage = db.query(TenantUsageDB).filter(TenantUsageDB.tenant_id == tenant_id).first()
    if usage:
        return usage
    usage = TenantUsageDB(tenant_id=tenant_id, messages_sent=0, documents_indexed=0)
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


def check_message_quota(db: Session, tenant_id: str, amount: int = 1):
    plan = _tenant_plan(db, tenant_id)
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])["messages"]
    usage = _usage_row(db, tenant_id)
    current = usage.messages_sent or 0
    if current + amount > limit:
        raise HTTPException(
            status_code=403,
            detail=f"Message quota exceeded for plan '{plan}'. Limit: {limit} messages.",
        )


def check_document_quota(db: Session, tenant_id: str, amount: int = 1):
    plan = _tenant_plan(db, tenant_id)
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])["documents"]
    usage = _usage_row(db, tenant_id)
    current = usage.documents_indexed or 0
    if current + amount > limit:
        raise HTTPException(
            status_code=403,
            detail=f"Document quota exceeded for plan '{plan}'. Limit: {limit} documents.",
        )


def remaining_document_slots(db: Session, tenant_id: str) -> int:
    plan = _tenant_plan(db, tenant_id)
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])["documents"]
    usage = _usage_row(db, tenant_id)
    current = usage.documents_indexed or 0
    return max(0, limit - current)
