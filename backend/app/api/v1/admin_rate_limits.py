from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.analytics import (
    RateLimitAlertSettingsPayload,
    RateLimitPolicyPayload,
    _get_or_create_alert_settings,
    _require_admin,
    create_rate_limit_policy,
    delete_rate_limit_policy,
    get_rate_limit_alerts,
    list_rate_limit_policies,
    update_rate_limit_notification_settings,
    update_rate_limit_policy,
)
from app.core.database import AdminAuditLogDB, RateLimitAlertDeliveryDB, TenantDB, get_db

router = APIRouter()


@router.get("/policies")
def admin_list_rate_limit_policies(
    tenant_filter: Optional[str] = Query(default=None),
    plan: Optional[str] = Query(default=None),
    route_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    return list_rate_limit_policies(tenant_filter, plan, route_key, db, context)


@router.post("/policies")
def admin_create_rate_limit_policy(
    payload: RateLimitPolicyPayload,
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    return create_rate_limit_policy(payload, db, context)


@router.put("/policies/{policy_id}")
def admin_update_rate_limit_policy(
    policy_id: int,
    payload: RateLimitPolicyPayload,
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    return update_rate_limit_policy(policy_id, payload, db, context)


@router.delete("/policies/{policy_id}")
def admin_delete_rate_limit_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    return delete_rate_limit_policy(policy_id, db, context)


@router.get("/alerts")
def admin_get_rate_limit_alerts(
    window_hours: int = Query(default=24, ge=1, le=168),
    min_hits: int = Query(default=5, ge=1, le=1000),
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    return get_rate_limit_alerts(window_hours, min_hits, db, context)


@router.get("/notifications")
def admin_get_rate_limit_notification_settings(
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    tenant_id = context["tenant_id"]
    row = _get_or_create_alert_settings(db, tenant_id)
    return {
        "tenant_id": tenant_id,
        "rate_limit_email_enabled": row.rate_limit_email_enabled,
        "rate_limit_email_recipient": row.rate_limit_email_recipient,
        "rate_limit_webhook_enabled": row.rate_limit_webhook_enabled,
        "rate_limit_webhook_url": row.rate_limit_webhook_url,
        "rate_limit_min_hits": row.rate_limit_min_hits,
        "rate_limit_window_minutes": row.rate_limit_window_minutes,
        "rate_limit_cooldown_minutes": row.rate_limit_cooldown_minutes,
    }


@router.put("/notifications")
def admin_update_rate_limit_notification_settings(
    payload: RateLimitAlertSettingsPayload,
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    return update_rate_limit_notification_settings(payload, db, context)


@router.get("/deliveries")
def admin_list_rate_limit_deliveries(
    tenant_filter: Optional[str] = Query(default=None),
    route_key: Optional[str] = Query(default=None),
    channel: Optional[str] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    query = (
        db.query(RateLimitAlertDeliveryDB, TenantDB.name.label("tenant_name"), TenantDB.plan.label("tenant_plan"))
        .outerjoin(TenantDB, TenantDB.id == RateLimitAlertDeliveryDB.tenant_id)
    )
    if tenant_filter:
        query = query.filter(RateLimitAlertDeliveryDB.tenant_id == tenant_filter)
    if route_key:
        query = query.filter(RateLimitAlertDeliveryDB.route_key == route_key)
    if channel:
        query = query.filter(RateLimitAlertDeliveryDB.channel == channel)

    total = query.count()
    rows = (
        query.order_by(RateLimitAlertDeliveryDB.last_sent_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    return {
        "pagination": {
            "offset": offset,
            "limit": limit,
            "returned": len(rows),
            "total": total,
            "has_more": offset + len(rows) < total,
        },
        "filters": {
            "tenant_filter": tenant_filter,
            "route_key": route_key,
            "channel": channel,
        },
        "counts": {
            "recent": sum(1 for row, _, _ in rows if row.last_sent_at and row.last_sent_at >= cutoff),
            "email": sum(1 for row, _, _ in rows if row.channel == "email"),
            "webhook": sum(1 for row, _, _ in rows if row.channel == "webhook"),
        },
        "items": [
            {
                "tenant_id": row.tenant_id,
                "tenant_name": tenant_name or row.tenant_id,
                "plan": tenant_plan or "starter",
                "route_key": row.route_key,
                "channel": row.channel,
                "hits": row.hits,
                "last_sent_at": row.last_sent_at.isoformat() if row.last_sent_at else None,
                "recent": bool(row.last_sent_at and row.last_sent_at >= cutoff),
            }
            for row, tenant_name, tenant_plan in rows
        ]
    }


@router.get("/audit")
def admin_list_rate_limit_audit_log(
    action: Optional[str] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    query = db.query(AdminAuditLogDB).filter(
        AdminAuditLogDB.action.like("rate_limit_%") | (AdminAuditLogDB.target_type == "tenant_alert_settings")
    )
    if action:
        query = query.filter(AdminAuditLogDB.action == action)
    if target_type:
        query = query.filter(AdminAuditLogDB.target_type == target_type)
    total = query.count()
    rows = (
        query.order_by(AdminAuditLogDB.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "pagination": {
            "offset": offset,
            "limit": limit,
            "returned": len(rows),
            "total": total,
            "has_more": offset + len(rows) < total,
        },
        "filters": {
            "action": action,
            "target_type": target_type,
        },
        "items": [
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "actor_tenant_id": row.actor_tenant_id,
                "actor_role": row.actor_role,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "metadata_json": row.metadata_json,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }
