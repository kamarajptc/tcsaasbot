from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session
from typing import List
import json
from pydantic import BaseModel

from app.core.logging import logger
from app.core.config import get_settings

from app.core.database import get_db, MessageDB, ConversationDB, TenantDB, TenantUsageDB, RateLimitPolicyDB, RateLimitEventDB
from app.models.bot import Bot, BotFAQ
from app.models.schemas import (
    BotCreate, BotUpdate, BotResponse, AnalyticsSummary, 
    MessageResponse, ConversationResponse, FAQCreate, FAQUpdate, 
    FAQResponse, TenantSettings, PublicBotResponse
)
from app.core.security import get_current_user_id
from app.core.rate_limit import get_effective_rate_limits_sync

router = APIRouter()
settings = get_settings()

BOT_NOT_FOUND = "Bot not found"


class CreateConversationRequest(BaseModel):
    bot_id: int

@router.post("/", response_model=BotResponse)
def create_bot(bot: BotCreate, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    bot_data = bot.model_dump()
    # tools is already a list coming from Pydantic, and SQLAlchemy JSON type handles it
        
    db_bot = Bot(**bot_data, tenant_id=tenant_id)
    db.add(db_bot)
    db.commit()
    db.refresh(db_bot)
    logger.info("bot_created", extra={
        "bot_id": db_bot.id, "bot_name": db_bot.name, "tenant_id": tenant_id
    })
    return db_bot

@router.get("/", response_model=List[BotResponse])
def read_bots(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    bots = db.query(Bot).filter(Bot.tenant_id == tenant_id).offset(skip).limit(limit).all()
    return bots

@router.get("/analytics/summary", response_model=AnalyticsSummary)
def get_analytics_summary(db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    total_conversations = db.query(ConversationDB).filter(ConversationDB.tenant_id == tenant_id).count()
    active_bots = db.query(Bot).filter(Bot.tenant_id == tenant_id, Bot.is_active == True).count()
    total_messages = db.query(MessageDB).join(ConversationDB).filter(ConversationDB.tenant_id == tenant_id).count()

    return {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "active_bots": active_bots,
        "avg_response_time": 1.5
    }

@router.get("/conversations", response_model=List[ConversationResponse])
def read_conversations(
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    convs = db.query(
        ConversationDB,
        Bot.name.label("bot_name")
    ).outerjoin(Bot, ConversationDB.bot_id == Bot.id)\
     .filter(ConversationDB.tenant_id == tenant_id)

    if status in {"new", "open", "pending", "resolved"}:
        convs = convs.filter(ConversationDB.status == status)

    convs = convs\
     .order_by(ConversationDB.created_at.desc()).all()
    
    results = []
    for conv, bot_name in convs:
        last_msg = db.query(MessageDB).filter(MessageDB.conversation_id == conv.id).order_by(MessageDB.created_at.desc()).first()
        msg_count = db.query(MessageDB).filter(MessageDB.conversation_id == conv.id).count()
        if q:
            q_lower = q.lower()
            haystack = f"{bot_name or ''} {last_msg.text if last_msg else ''}".lower()
            if q_lower not in haystack:
                continue
        
        results.append({
            "id": conv.id,
            "bot_id": conv.bot_id,
            "bot_name": bot_name,
            "status": conv.status,
            "agent_requested": bool(conv.agent_requested),
            "created_at": conv.created_at,
            "last_message": last_msg.text if last_msg else "No messages",
            "last_message_sender": last_msg.sender if last_msg else None,
            "message_count": msg_count
        })
        
    return results


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    request: CreateConversationRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id)
):
    bot = db.query(Bot).filter(Bot.id == request.bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)

    conv = ConversationDB(tenant_id=tenant_id, bot_id=request.bot_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {
        "id": conv.id,
        "bot_id": conv.bot_id,
        "bot_name": bot.name,
        "status": conv.status,
        "agent_requested": bool(conv.agent_requested),
        "created_at": conv.created_at,
        "last_message": "No messages",
        "last_message_sender": None,
        "message_count": 0
    }


@router.delete("/bots/{bot_id}/conversations")
def clear_bot_conversations(
    bot_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id)
):
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)

    conv_ids = [
        cid for (cid,) in db.query(ConversationDB.id)
        .filter(ConversationDB.tenant_id == tenant_id, ConversationDB.bot_id == bot_id)
        .all()
    ]
    if conv_ids:
        db.query(MessageDB).filter(MessageDB.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
        db.query(ConversationDB).filter(ConversationDB.id.in_(conv_ids)).delete(synchronize_session=False)
        db.commit()
    return {"ok": True, "deleted_conversations": len(conv_ids)}

@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
def read_conversation_messages(conversation_id: int, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    conv = db.query(ConversationDB).filter(ConversationDB.id == conversation_id, ConversationDB.tenant_id == tenant_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    messages = db.query(MessageDB).filter(MessageDB.conversation_id == conversation_id).order_by(MessageDB.created_at.asc()).all()
    return messages

@router.get("/settings", response_model=TenantSettings)
def get_settings(db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
    if not tenant:
        tenant = TenantDB(id=tenant_id, name="New User")
        db.add(tenant)
        db.commit()
    
    usage = db.query(TenantUsageDB).filter(TenantUsageDB.tenant_id == tenant_id).first()
    if not usage:
        usage = TenantUsageDB(tenant_id=tenant_id)
        db.add(usage)
        db.commit()
        db.refresh(usage)
        
    limits = {
        "starter": {"msgs": 100, "docs": 5},
        "pro": {"msgs": 5000, "docs": 50},
        "enterprise": {"msgs": 100000, "docs": 1000}
    }
    
    plan_limits = limits.get(tenant.plan, limits["starter"])
    rate_limits = get_effective_rate_limits_sync(tenant_id, session_factory=lambda: db)
    window_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    recent_events = (
        db.query(RateLimitEventDB.route_key, func.count(RateLimitEventDB.id).label("hits"))
        .filter(
            RateLimitEventDB.tenant_id == tenant_id,
            RateLimitEventDB.exceeded_at >= window_start,
        )
        .group_by(RateLimitEventDB.route_key)
        .order_by(func.count(RateLimitEventDB.id).desc())
        .all()
    )
    total_throttled = sum(int(row.hits) for row in recent_events)
    hottest_route = recent_events[0].route_key if recent_events else None
    upgrade_recommended = total_throttled >= 5 or (hottest_route == "chat_public" and total_throttled >= 3)

    return {
        "id": tenant.id,
        "name": tenant.name,
        "plan": tenant.plan,
        "messages_sent": usage.messages_sent,
        "documents_indexed": usage.documents_indexed,
        "message_limit": plan_limits["msgs"],
        "document_limit": plan_limits["docs"],
        "rate_limits": rate_limits,
        "rate_limit_summary": {
            "window_hours": 24,
            "total_throttled_requests": total_throttled,
            "top_throttled_routes": [
                {"route_key": row.route_key, "count": int(row.hits)}
                for row in recent_events[:5]
            ],
            "upgrade_recommended": upgrade_recommended,
        },
        "support": {
            "email": settings.SUPPORT_EMAIL,
            "url": settings.SUPPORT_URL,
        },
    }


@router.get("/rate-limits")
def get_rate_limit_overview(
    window_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
    plan = tenant.plan if tenant and tenant.plan else "starter"
    effective_limits = get_effective_rate_limits_sync(tenant_id, session_factory=lambda: db)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=window_hours)
    recent_events = (
        db.query(RateLimitEventDB)
        .filter(
            RateLimitEventDB.tenant_id == tenant_id,
            RateLimitEventDB.exceeded_at >= since,
        )
        .order_by(RateLimitEventDB.exceeded_at.desc())
        .all()
    )
    route_counts = {}
    for event in recent_events:
        route_counts[event.route_key] = route_counts.get(event.route_key, 0) + 1

    return {
        "tenant_id": tenant_id,
        "plan": plan,
        "window_hours": window_hours,
        "effective_limits": effective_limits,
        "total_throttled_requests": len(recent_events),
        "top_throttled_routes": [
            {"route_key": route_key, "count": count}
            for route_key, count in sorted(route_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        ],
        "recent_events": [
            {
                "route_key": event.route_key,
                "request_path": event.request_path,
                "limit": event.limit_value,
                "retry_after_seconds": event.retry_after_seconds,
                "exceeded_at": event.exceeded_at.isoformat() if event.exceeded_at else None,
            }
            for event in recent_events[:20]
        ],
        "support": {
            "email": settings.SUPPORT_EMAIL,
            "url": settings.SUPPORT_URL,
            "message": "If you see repeated throttling, contact support for a plan review or tenant-specific override.",
        },
    }

@router.get("/public/{bot_id}", response_model=PublicBotResponse)
def get_bot_public(bot_id: int, db: Session = Depends(get_db)):
    db_bot = db.query(Bot).filter(Bot.id == bot_id, Bot.is_active == True).first()
    if not db_bot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    return db_bot

@router.get("/{bot_id}", response_model=BotResponse)
def read_bot(bot_id: int, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    db_bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not db_bot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    return db_bot

@router.put("/{bot_id}", response_model=BotResponse)
def update_bot(bot_id: int, bot_update: BotUpdate, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    db_bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not db_bot:
        logger.warning("bot_not_found", extra={"bot_id": bot_id, "tenant_id": tenant_id, "action": "update"})
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    
    update_data = bot_update.model_dump(exclude_unset=True)
    # tools is handled by JSON type
        
    for key, value in update_data.items():
        setattr(db_bot, key, value)
        
    db.commit()
    db.refresh(db_bot)
    logger.info("bot_updated", extra={
        "bot_id": bot_id, "tenant_id": tenant_id,
        "updated_fields": list(update_data.keys())
    })
    return db_bot

@router.delete("/{bot_id}")
def delete_bot(bot_id: int, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    db_bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not db_bot:
        logger.warning("bot_not_found", extra={"bot_id": bot_id, "tenant_id": tenant_id, "action": "delete"})
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
        
    db.delete(db_bot)
    db.commit()
    logger.info("bot_deleted", extra={"bot_id": bot_id, "tenant_id": tenant_id})
    return {"ok": True}

@router.get("/{bot_id}/faqs", response_model=List[FAQResponse])
def get_bot_faqs(bot_id: int, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    db_bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not db_bot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    
    faqs = db.query(BotFAQ).filter(BotFAQ.bot_id == bot_id).all()
    return faqs

@router.post("/{bot_id}/faqs", response_model=FAQResponse)
def create_bot_faq(bot_id: int, faq: FAQCreate, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    db_bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not db_bot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    
    db_faq = BotFAQ(**faq.model_dump(), bot_id=bot_id)
    db.add(db_faq)
    db.commit()
    db.refresh(db_faq)
    logger.info("faq_created", extra={
        "faq_id": db_faq.id, "bot_id": bot_id, "tenant_id": tenant_id
    })
    return db_faq

@router.put("/{bot_id}/faqs/{faq_id}", response_model=FAQResponse)
def update_bot_faq(bot_id: int, faq_id: int, faq_update: FAQUpdate, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    db_bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not db_bot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    
    db_faq = db.query(BotFAQ).filter(BotFAQ.id == faq_id, BotFAQ.bot_id == bot_id).first()
    if not db_faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    update_data = faq_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_faq, key, value)
        
    db.commit()
    db.refresh(db_faq)
    return db_faq

@router.delete("/{bot_id}/faqs/{faq_id}")
def delete_bot_faq(bot_id: int, faq_id: int, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    db_bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not db_bot:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND)
    
    db_faq = db.query(BotFAQ).filter(BotFAQ.id == faq_id, BotFAQ.bot_id == bot_id).first()
    if not db_faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
        
    db.delete(db_faq)
    db.commit()
    logger.info("faq_deleted", extra={
        "faq_id": faq_id, "bot_id": bot_id, "tenant_id": tenant_id
    })
    return {"ok": True}
