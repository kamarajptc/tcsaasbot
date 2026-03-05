from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import json

from app.core.database import (
    get_db,
    AdminAuditLogDB,
    LeadDB,
    ConversationDB,
    MessageDB,
    TenantUsageDB,
    RateLimitEventDB,
    RateLimitPolicyDB,
    TenantDB,
    TenantAlertSettingsDB,
)
from app.core.security import get_current_user_id, get_current_user_context
from app.core.logging import logger
from app.core.config import get_settings
from app.core.rate_limit import clear_rate_limit_policy_cache, get_effective_rate_limits_sync
from pydantic import BaseModel, Field

router = APIRouter()
settings = get_settings()


class RateLimitPolicyPayload(BaseModel):
    tenant_id: Optional[str] = None
    plan: Optional[str] = Field(default=None, pattern="^(starter|pro|enterprise)$")
    route_key: str = Field(..., min_length=1, max_length=80)
    rpm_limit: int = Field(..., ge=1, le=100000)
    is_active: bool = True


class RateLimitAlertSettingsPayload(BaseModel):
    rate_limit_email_enabled: bool = False
    rate_limit_email_recipient: Optional[str] = Field(default=None, max_length=255)
    rate_limit_webhook_enabled: bool = False
    rate_limit_webhook_url: Optional[str] = Field(default=None, max_length=500)
    rate_limit_min_hits: int = Field(default=5, ge=1, le=1000)
    rate_limit_window_minutes: int = Field(default=60, ge=1, le=1440)
    rate_limit_cooldown_minutes: int = Field(default=1, ge=1, le=1440)


def _require_admin(context: dict = Depends(get_current_user_context)) -> dict:
    role = (context.get("role") or "admin").lower()
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return context


def _safe_json(value: str | None) -> Dict:
    if not value:
        return {}
    try:
        obj = json.loads(value)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _validate_policy_scope(payload: RateLimitPolicyPayload) -> None:
    has_tenant = bool(payload.tenant_id)
    has_plan = bool(payload.plan)
    if has_tenant == has_plan:
        raise HTTPException(status_code=400, detail="Provide exactly one scope: tenant_id or plan")


def _find_duplicate_policy(db: Session, payload: RateLimitPolicyPayload, exclude_id: Optional[int] = None):
    query = db.query(RateLimitPolicyDB).filter(
        RateLimitPolicyDB.route_key == payload.route_key,
        RateLimitPolicyDB.tenant_id == payload.tenant_id,
        RateLimitPolicyDB.plan == payload.plan,
    )
    if exclude_id is not None:
        query = query.filter(RateLimitPolicyDB.id != exclude_id)
    return query.first()


def _get_or_create_alert_settings(db: Session, tenant_id: str) -> TenantAlertSettingsDB:
    row = db.query(TenantAlertSettingsDB).filter(TenantAlertSettingsDB.tenant_id == tenant_id).first()
    if row:
        return row
    row = TenantAlertSettingsDB(
        tenant_id=tenant_id,
        rate_limit_email_enabled=False,
        rate_limit_email_recipient=None,
        rate_limit_webhook_enabled=False,
        rate_limit_webhook_url=None,
        rate_limit_min_hits=settings.RATE_LIMIT_ALERT_DEFAULT_MIN_HITS,
        rate_limit_window_minutes=settings.RATE_LIMIT_ALERT_DEFAULT_WINDOW_MINUTES,
        rate_limit_cooldown_minutes=settings.RATE_LIMIT_ALERT_DEFAULT_COOLDOWN_MINUTES,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _write_admin_audit_log(
    db: Session,
    *,
    actor_tenant_id: str,
    actor_role: str,
    tenant_id: str,
    action: str,
    target_type: str,
    target_id: Optional[str],
    metadata: Dict,
) -> None:
    db.add(
        AdminAuditLogDB(
            tenant_id=tenant_id,
            actor_tenant_id=actor_tenant_id,
            actor_role=actor_role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_json=json.dumps(metadata),
        )
    )
    db.commit()

@router.get("/summary")
def get_analytics_summary(db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    """
    Returns high-level metric cards for the dashboard.
    """
    total_leads = db.query(LeadDB).filter(LeadDB.tenant_id == tenant_id).count()
    total_conversations = db.query(ConversationDB).filter(ConversationDB.tenant_id == tenant_id).count()
    
    # Calculate conversion rate
    conversion_rate = (total_leads / total_conversations * 100) if total_conversations > 0 else 0
    
    usage = db.query(TenantUsageDB).filter(TenantUsageDB.tenant_id == tenant_id).first()
    messages_sent = usage.messages_sent if usage else 0
    
    logger.info("analytics_summary_fetched", extra={
        "tenant_id": tenant_id, "total_leads": total_leads,
        "total_conversations": total_conversations, "conversion_rate": round(conversion_rate, 1)
    })

    return {
        "total_leads": total_leads,
        "total_conversations": total_conversations,
        "conversion_rate": round(conversion_rate, 1),
        "messages_sent": messages_sent
    }

@router.get("/trends")
def get_analytics_trends(db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    """
    Returns daily trends for leads and conversations for the last 7 days.
    """
    end_date = datetime.now(timezone.utc).replace(tzinfo=None)
    start_date = end_date - timedelta(days=6)
    
    # Initialize trend dictionary
    trends = {}
    for i in range(7):
        date_str = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        trends[date_str] = {"leads": 0, "conversations": 0}
        
    # Fetch lead trends
    lead_query = db.query(
        func.date(LeadDB.created_at).label('date'),
        func.count(LeadDB.id).label('count')
    ).filter(
        LeadDB.tenant_id == tenant_id,
        LeadDB.created_at >= start_date
    ).group_by(func.date(LeadDB.created_at)).all()
    
    for row in lead_query:
        # row.date might be a string or date object depending on DB backend
        d_str = str(row.date)
        if d_str in trends:
            trends[d_str]["leads"] = row.count
            
    # Fetch conversation trends
    conv_query = db.query(
        func.date(ConversationDB.created_at).label('date'),
        func.count(ConversationDB.id).label('count')
    ).filter(
        ConversationDB.tenant_id == tenant_id,
        ConversationDB.created_at >= start_date
    ).group_by(func.date(ConversationDB.created_at)).all()
    
    for row in conv_query:
        d_str = str(row.date)
        if d_str in trends:
            trends[d_str]["conversations"] = row.count
            
    # Flatten to list for frontend charts
    result = []
    for date_str, vals in sorted(trends.items()):
        result.append({
            "date": date_str,
            "leads": vals["leads"],
            "conversations": vals["conversations"]
        })
        
    return result

@router.get("/bot-performance")
def get_bot_performance(db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    """
    Returns breakdown of leads and messages per bot.
    """
    from app.models.bot import Bot
    bots = db.query(Bot).filter(Bot.tenant_id == tenant_id).all()
    
    performance = []
    for bot in bots:
        leads = db.query(LeadDB).filter(LeadDB.bot_id == bot.id).count()
        convs = db.query(ConversationDB).filter(ConversationDB.bot_id == bot.id).count()
        
        performance.append({
            "bot_name": bot.name,
            "leads": leads,
            "conversations": convs,
            "id": bot.id
        })
        
    return performance


@router.get("/rate-limits/summary")
def get_rate_limit_summary(
    window_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=window_hours)
    tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
    plan = (tenant.plan if tenant and tenant.plan else "starter").lower()

    events = (
        db.query(RateLimitEventDB)
        .filter(
            RateLimitEventDB.tenant_id == tenant_id,
            RateLimitEventDB.exceeded_at >= since,
        )
        .order_by(RateLimitEventDB.exceeded_at.desc())
        .all()
    )
    route_counts: Dict[str, int] = {}
    for event in events:
        route_counts[event.route_key] = route_counts.get(event.route_key, 0) + 1

    effective_limits = get_effective_rate_limits_sync(tenant_id, session_factory=lambda: db)

    recent = [
        {
            "route_key": event.route_key,
            "request_path": event.request_path,
            "limit": event.limit_value,
            "retry_after_seconds": event.retry_after_seconds,
            "exceeded_at": event.exceeded_at.isoformat() if event.exceeded_at else None,
        }
        for event in events[:20]
    ]

    return {
        "tenant_id": tenant_id,
        "plan": plan,
        "window_hours": window_hours,
        "total_throttled_requests": len(events),
        "effective_limits": effective_limits,
        "top_throttled_routes": [
            {"route_key": route_key, "count": count}
            for route_key, count in sorted(route_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        "recent_events": recent,
        "support": {
            "email": settings.SUPPORT_EMAIL,
            "url": settings.SUPPORT_URL,
        },
    }


@router.get("/rate-limits/policies")
def list_rate_limit_policies(
    tenant_filter: Optional[str] = Query(default=None),
    plan: Optional[str] = Query(default=None),
    route_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    query = db.query(RateLimitPolicyDB)
    if tenant_filter is not None:
        if tenant_filter == "__global__":
            query = query.filter(RateLimitPolicyDB.tenant_id.is_(None))
        else:
            query = query.filter(RateLimitPolicyDB.tenant_id == tenant_filter)
    if plan:
        query = query.filter(RateLimitPolicyDB.plan == plan)
    if route_key:
        query = query.filter(RateLimitPolicyDB.route_key == route_key)
    rows = query.order_by(RateLimitPolicyDB.tenant_id.asc().nullsfirst(), RateLimitPolicyDB.plan.asc().nullsfirst(), RateLimitPolicyDB.route_key.asc()).all()
    return {
        "items": [
            {
                "id": row.id,
                "scope": "tenant" if row.tenant_id else "plan",
                "tenant_id": row.tenant_id,
                "plan": row.plan,
                "route_key": row.route_key,
                "rpm_limit": row.rpm_limit,
                "is_active": row.is_active,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.post("/rate-limits/policies")
def create_rate_limit_policy(
    payload: RateLimitPolicyPayload,
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    _validate_policy_scope(payload)
    if _find_duplicate_policy(db, payload):
        raise HTTPException(status_code=409, detail="Rate limit policy already exists for this scope and route")
    row = RateLimitPolicyDB(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    clear_rate_limit_policy_cache(payload.tenant_id)
    _write_admin_audit_log(
        db,
        actor_tenant_id=context["tenant_id"],
        actor_role=context.get("role", "admin"),
        tenant_id=payload.tenant_id or context["tenant_id"],
        action="rate_limit_policy_created",
        target_type="rate_limit_policy",
        target_id=str(row.id),
        metadata=payload.model_dump(),
    )
    return {
        "id": row.id,
        "scope": "tenant" if row.tenant_id else "plan",
        "tenant_id": row.tenant_id,
        "plan": row.plan,
        "route_key": row.route_key,
        "rpm_limit": row.rpm_limit,
        "is_active": row.is_active,
    }


@router.put("/rate-limits/policies/{policy_id}")
def update_rate_limit_policy(
    policy_id: int,
    payload: RateLimitPolicyPayload,
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    row = db.query(RateLimitPolicyDB).filter(RateLimitPolicyDB.id == policy_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rate limit policy not found")
    data = payload.model_dump()
    _validate_policy_scope(payload)
    if _find_duplicate_policy(db, payload, exclude_id=policy_id):
        raise HTTPException(status_code=409, detail="Rate limit policy already exists for this scope and route")
    previous_tenant_id = row.tenant_id
    before = {
        "tenant_id": row.tenant_id,
        "plan": row.plan,
        "route_key": row.route_key,
        "rpm_limit": row.rpm_limit,
        "is_active": row.is_active,
    }
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    clear_rate_limit_policy_cache(previous_tenant_id)
    clear_rate_limit_policy_cache(row.tenant_id)
    _write_admin_audit_log(
        db,
        actor_tenant_id=context["tenant_id"],
        actor_role=context.get("role", "admin"),
        tenant_id=row.tenant_id or context["tenant_id"],
        action="rate_limit_policy_updated",
        target_type="rate_limit_policy",
        target_id=str(row.id),
        metadata={"before": before, "after": data},
    )
    return {
        "id": row.id,
        "scope": "tenant" if row.tenant_id else "plan",
        "tenant_id": row.tenant_id,
        "plan": row.plan,
        "route_key": row.route_key,
        "rpm_limit": row.rpm_limit,
        "is_active": row.is_active,
    }


@router.delete("/rate-limits/policies/{policy_id}")
def delete_rate_limit_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    row = db.query(RateLimitPolicyDB).filter(RateLimitPolicyDB.id == policy_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rate limit policy not found")
    tenant_id = row.tenant_id
    deleted = {
        "tenant_id": row.tenant_id,
        "plan": row.plan,
        "route_key": row.route_key,
        "rpm_limit": row.rpm_limit,
        "is_active": row.is_active,
    }
    db.delete(row)
    db.commit()
    clear_rate_limit_policy_cache(tenant_id)
    _write_admin_audit_log(
        db,
        actor_tenant_id=context["tenant_id"],
        actor_role=context.get("role", "admin"),
        tenant_id=tenant_id or context["tenant_id"],
        action="rate_limit_policy_deleted",
        target_type="rate_limit_policy",
        target_id=str(policy_id),
        metadata=deleted,
    )
    return {"ok": True, "id": policy_id}


@router.get("/rate-limits/alerts")
def get_rate_limit_alerts(
    window_hours: int = Query(default=24, ge=1, le=168),
    min_hits: int = Query(default=5, ge=1, le=1000),
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=window_hours)
    rows = (
        db.query(
            RateLimitEventDB.tenant_id,
            TenantDB.name,
            TenantDB.plan,
            RateLimitEventDB.route_key,
            func.count(RateLimitEventDB.id).label("hits"),
            func.max(RateLimitEventDB.exceeded_at).label("last_seen"),
        )
        .filter(RateLimitEventDB.exceeded_at >= since)
        .outerjoin(TenantDB, TenantDB.id == RateLimitEventDB.tenant_id)
        .group_by(
            RateLimitEventDB.tenant_id,
            TenantDB.name,
            TenantDB.plan,
            RateLimitEventDB.route_key,
        )
        .having(func.count(RateLimitEventDB.id) >= min_hits)
        .order_by(func.count(RateLimitEventDB.id).desc())
        .all()
    )
    items = [
        {
            "tenant_id": tenant_id or "anonymous",
            "tenant_name": tenant_name or tenant_id or "Unknown tenant",
            "plan": plan or "starter",
            "route_key": route_key,
            "hits": int(hits),
            "last_seen": last_seen.isoformat() if last_seen else None,
            "severity": "high" if hits >= (min_hits * 3) else "medium",
            "message": f"Tenant {tenant_id or 'anonymous'} exceeded {route_key} {hits} times in the last {window_hours}h.",
            "next_action": "Contact tenant and review a tenant override or plan upgrade." if hits >= (min_hits * 3) else "Monitor and reach out if throttling continues.",
            "support": {
                "email": settings.SUPPORT_EMAIL,
                "url": settings.SUPPORT_URL,
            },
        }
        for tenant_id, tenant_name, plan, route_key, hits, last_seen in rows
    ]
    return {
        "window_hours": window_hours,
        "min_hits": min_hits,
        "items": items,
    }


@router.get("/rate-limits/notifications")
def get_rate_limit_notification_settings(
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


@router.put("/rate-limits/notifications")
def update_rate_limit_notification_settings(
    payload: RateLimitAlertSettingsPayload,
    db: Session = Depends(get_db),
    context: dict = Depends(_require_admin),
):
    tenant_id = context["tenant_id"]
    row = _get_or_create_alert_settings(db, tenant_id)
    data = payload.model_dump()
    if data["rate_limit_email_enabled"] and not (data.get("rate_limit_email_recipient") or "").strip():
        raise HTTPException(status_code=400, detail="Email recipient is required when email alerts are enabled")
    if data["rate_limit_webhook_enabled"] and not (data.get("rate_limit_webhook_url") or "").strip():
        raise HTTPException(status_code=400, detail="Webhook URL is required when webhook alerts are enabled")
    before = {
        "rate_limit_email_enabled": row.rate_limit_email_enabled,
        "rate_limit_email_recipient": row.rate_limit_email_recipient,
        "rate_limit_webhook_enabled": row.rate_limit_webhook_enabled,
        "rate_limit_webhook_url": row.rate_limit_webhook_url,
        "rate_limit_min_hits": row.rate_limit_min_hits,
        "rate_limit_window_minutes": row.rate_limit_window_minutes,
        "rate_limit_cooldown_minutes": row.rate_limit_cooldown_minutes,
    }
    for key, value in data.items():
        setattr(row, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(row)
    _write_admin_audit_log(
        db,
        actor_tenant_id=context["tenant_id"],
        actor_role=context.get("role", "admin"),
        tenant_id=tenant_id,
        action="rate_limit_notification_settings_updated",
        target_type="tenant_alert_settings",
        target_id=tenant_id,
        metadata={"before": before, "after": data},
    )
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
@router.get("/ai-performance")
def get_ai_performance(bot_id: int = None, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    """
    Returns AI-specific performance metrics: deflection rate, transfers, and CSAT.
    """
    conv_query = db.query(ConversationDB).filter(ConversationDB.tenant_id == tenant_id)
    if bot_id:
        conv_query = conv_query.filter(ConversationDB.bot_id == bot_id)

    conversations = conv_query.all()
    total_convs = len(conversations)
    conv_ids = [c.id for c in conversations]

    transferred = sum(1 for c in conversations if bool(c.agent_requested))
    ai_resolved = sum(1 for c in conversations if c.status == "resolved" and not bool(c.agent_requested))
    unresolved = sum(1 for c in conversations if c.status in {"new", "open", "pending"})

    deflection_rate = (ai_resolved / total_convs * 100) if total_convs > 0 else 0.0
    transfer_rate = (transferred / total_convs * 100) if total_convs > 0 else 0.0

    # Response-time metric from user->(bot|agent) turn pairs.
    avg_response_ms = 0.0
    if conv_ids:
        msgs = (
            db.query(MessageDB)
            .filter(MessageDB.conversation_id.in_(conv_ids))
            .order_by(MessageDB.conversation_id.asc(), MessageDB.created_at.asc())
            .all()
        )
        deltas_ms = []
        last_user_ts_by_conv: Dict[int, datetime] = {}
        for msg in msgs:
            if msg.sender == "user":
                last_user_ts_by_conv[msg.conversation_id] = msg.created_at
                continue
            if msg.sender not in {"bot", "agent"}:
                continue
            user_ts = last_user_ts_by_conv.get(msg.conversation_id)
            if not user_ts:
                continue
            delta = (msg.created_at - user_ts).total_seconds() * 1000
            if delta >= 0:
                deltas_ms.append(delta)
                last_user_ts_by_conv.pop(msg.conversation_id, None)
        if deltas_ms:
            avg_response_ms = sum(deltas_ms) / len(deltas_ms)

    # Lifecycle-based satisfaction proxy (no static mock constants).
    csat = 3.2 + (deflection_rate / 100.0) * 1.4 - (transfer_rate / 100.0) * 0.4
    if total_convs == 0:
        csat = 0.0
    csat = max(0.0, min(5.0, csat))

    end_date = datetime.now(timezone.utc).replace(tzinfo=None)
    start_date = end_date - timedelta(days=6)
    daily = {
        (start_date + timedelta(days=i)).strftime("%Y-%m-%d"): {"ai": 0, "human": 0, "abandoned": 0}
        for i in range(7)
    }
    for conv in conversations:
        d_key = conv.created_at.strftime("%Y-%m-%d")
        if d_key not in daily:
            continue
        if conv.agent_requested:
            daily[d_key]["human"] += 1
        elif conv.status == "resolved":
            daily[d_key]["ai"] += 1
        else:
            daily[d_key]["abandoned"] += 1
    trend = [
        {
            "date": datetime.strptime(day, "%Y-%m-%d").strftime("%a"),
            "ai": vals["ai"],
            "human": vals["human"],
            "abandoned": vals["abandoned"],
        }
        for day, vals in sorted(daily.items())
    ]

    top_topics = []
    if conv_ids:
        user_msgs = (
            db.query(MessageDB)
            .filter(MessageDB.conversation_id.in_(conv_ids), MessageDB.sender == "user")
            .order_by(MessageDB.created_at.desc())
            .all()
        )
        counts: Dict[str, Dict[str, int | str]] = {}
        for msg in user_msgs:
            text = (msg.text or "").strip()
            if not text:
                continue
            low = text.lower()
            if "?" not in text and not low.startswith(("what", "how", "why", "can", "do", "does", "where", "when", "is", "are")):
                continue
            key = low[:80]
            row = counts.get(key)
            if not row:
                row = {"topic": text[:120], "count": 0}
                counts[key] = row
            row["count"] = int(row["count"]) + 1
        ranked = sorted(counts.values(), key=lambda r: int(r["count"]), reverse=True)[:3]
        for row in ranked:
            count = int(row["count"])
            impact = "High" if count >= 5 else ("Medium" if count >= 2 else "Low")
            top_topics.append({"topic": row["topic"], "count": count, "impact": impact})

    recent_transfers = []
    transfer_convs = [c for c in sorted(conversations, key=lambda c: c.created_at, reverse=True) if c.agent_requested][:8]
    for conv in transfer_convs:
        last_user = (
            db.query(MessageDB)
            .filter(MessageDB.conversation_id == conv.id, MessageDB.sender == "user")
            .order_by(MessageDB.created_at.desc())
            .first()
        )
        recent_transfers.append({
            "id": conv.id,
            "user": f"Conversation #{conv.id}",
            "reason": (last_user.text[:160] if last_user and last_user.text else "Agent transfer requested"),
            "time": conv.created_at.strftime("%Y-%m-%d %H:%M"),
        })

    logger.info("ai_performance_computed", extra={
        "tenant_id": tenant_id,
        "bot_id": bot_id,
        "total_conversations": total_convs,
        "ai_resolved": ai_resolved,
        "transferred": transferred,
        "unresolved": unresolved,
        "deflection_rate": round(deflection_rate, 2),
        "transfer_rate": round(transfer_rate, 2),
    })

    return {
        "total_ai_chats": total_convs,
        "resolution_rate": round(deflection_rate, 1),
        "transfer_rate": round(transfer_rate, 1),
        "avg_response_time": f"{round(avg_response_ms / 1000, 2)}s",
        "csat": round(csat, 1),
        "deflection_trend": trend,
        "top_topics": top_topics,
        "recent_transfers": recent_transfers,
    }


@router.get("/faq-suggestions")
def get_faq_suggestions(
    bot_id: int = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    """
    Generate FAQ suggestions from real conversation data.
    Heuristic:
    - focus on user questions
    - prioritize unresolved or weak bot-response turns
    """
    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50

    conv_query = db.query(ConversationDB).filter(ConversationDB.tenant_id == tenant_id)
    if bot_id:
        conv_query = conv_query.filter(ConversationDB.bot_id == bot_id)
    conv_ids = [cid for (cid,) in conv_query.with_entities(ConversationDB.id).all()]
    if not conv_ids:
        return []

    messages = (
        db.query(MessageDB)
        .filter(MessageDB.conversation_id.in_(conv_ids))
        .order_by(MessageDB.conversation_id.asc(), MessageDB.created_at.asc())
        .all()
    )

    grouped = {}
    for msg in messages:
        grouped.setdefault(msg.conversation_id, []).append(msg)

    weak_markers = [
        "not available", "not found", "temporarily at capacity", "could not", "can't", "cannot"
    ]
    candidate_counts = {}

    for conv_msgs in grouped.values():
        for idx, msg in enumerate(conv_msgs):
            if msg.sender != "user":
                continue
            text = (msg.text or "").strip()
            low = text.lower()
            looks_like_question = ("?" in text) or low.startswith(
                ("what", "how", "why", "can", "do", "does", "where", "when", "is", "are")
            )
            if not looks_like_question:
                continue

            next_bot = None
            for follow in conv_msgs[idx + 1:]:
                if follow.sender == "bot":
                    next_bot = follow
                    break

            unresolved = next_bot is None
            if next_bot is not None:
                ans_low = (next_bot.text or "").lower()
                unresolved = any(marker in ans_low for marker in weak_markers)

            if unresolved:
                key = low[:180]
                candidate_counts[key] = {
                    "question": text[:300],
                    "count": candidate_counts.get(key, {}).get("count", 0) + 1,
                }

    ranked = sorted(candidate_counts.values(), key=lambda item: item["count"], reverse=True)[:limit]
    suggestions = []
    for row in ranked:
        question = row["question"]
        suggestions.append({
            "question": question,
            "answer": f"Thanks for asking about '{question}'. We are preparing a verified answer for this topic.",
            "count": row["count"],
            "source": "conversation_mining",
        })
    return suggestions


@router.get("/customers/realtime")
def get_customers_realtime(
    status: str = Query(default="all"),
    bot_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    conv_query = db.query(ConversationDB).filter(ConversationDB.tenant_id == tenant_id)
    if status != "all":
        conv_query = conv_query.filter(ConversationDB.status == status)
    if bot_id is not None:
        conv_query = conv_query.filter(ConversationDB.bot_id == bot_id)

    total_count = conv_query.count()
    conversations = (
        conv_query
        .order_by(ConversationDB.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Lightweight explicit bot lookup.
    from app.models.bot import Bot
    bot_lookup = {b.id: b.name for b in db.query(Bot).filter(Bot.tenant_id == tenant_id).all()}

    rows = []
    for conv in conversations:
        messages = (
            db.query(MessageDB)
            .filter(MessageDB.conversation_id == conv.id)
            .order_by(MessageDB.created_at.asc())
            .all()
        )
        msg_count = len(messages)
        last_message = messages[-1] if messages else None
        last_user_message = next((m for m in reversed(messages) if m.sender == "user"), None)
        last_agent_or_bot = next((m for m in reversed(messages) if m.sender in {"bot", "agent"}), None)

        lead = (
            db.query(LeadDB)
            .filter(LeadDB.tenant_id == tenant_id, LeadDB.conversation_id == conv.id)
            .order_by(LeadDB.created_at.desc())
            .first()
        )
        lead_data = _safe_json(lead.data if lead else None)
        customer_name = (
            lead_data.get("name")
            or lead_data.get("full_name")
            or lead_data.get("email")
            or f"Visitor #{conv.id}"
        )
        customer_email = lead_data.get("email")

        if q:
            hay = f"{customer_name} {customer_email or ''} {(last_message.text if last_message else '')}".lower()
            if q.lower() not in hay:
                continue

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        wait_seconds = 0
        if last_user_message and (
            last_agent_or_bot is None or last_user_message.created_at > last_agent_or_bot.created_at
        ):
            wait_seconds = int(max(0, (now - last_user_message.created_at).total_seconds()))

        rows.append({
            "conversation_id": conv.id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "status": conv.status,
            "priority": conv.priority,
            "agent_requested": bool(conv.agent_requested),
            "bot_id": conv.bot_id,
            "bot_name": bot_lookup.get(conv.bot_id, "Unknown Bot") if conv.bot_id else "Unassigned",
            "message_count": msg_count,
            "last_message": (last_message.text[:220] if last_message and last_message.text else ""),
            "last_message_at": last_message.created_at.isoformat() if last_message else conv.created_at.isoformat(),
            "created_at": conv.created_at.isoformat(),
            "wait_seconds": wait_seconds,
            "country": lead.country if lead else None,
            "source": lead.source if lead else None,
        })

    kpi_convs = db.query(ConversationDB).filter(ConversationDB.tenant_id == tenant_id).all()
    open_count = sum(1 for c in kpi_convs if c.status in {"new", "open", "pending"})
    resolved_count = sum(1 for c in kpi_convs if c.status == "resolved")
    transfer_count = sum(1 for c in kpi_convs if bool(c.agent_requested))

    avg_wait = 0
    if rows:
        avg_wait = int(sum(r["wait_seconds"] for r in rows) / len(rows))

    return {
        "summary": {
            "total_customers": total_count,
            "open_conversations": open_count,
            "resolved_conversations": resolved_count,
            "transfer_requested": transfer_count,
            "avg_wait_seconds": avg_wait,
        },
        "items": rows,
        "limit": limit,
        "offset": offset,
    }
