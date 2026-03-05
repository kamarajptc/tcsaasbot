from datetime import datetime
import asyncio
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import httpx

from app.core.database import AgentTransferRuleDB, ConversationDB, MessageDB, get_db
from app.core.logging import logger
from app.core.security import get_current_user_id
from app.core.url_security import is_safe_outbound_url
from app.models.bot import Bot
from app.services.email_service import email_service
from app.services.integration_service import integration_service

router = APIRouter()


class TransferRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    rule_type: str = Field(..., pattern="^(keyword|time|manual)$")
    condition: str = Field(..., min_length=1, max_length=500)
    action: str = Field(default="transfer", pattern="^(transfer|notify)$")
    transfer_message: Optional[str] = None
    notify_email: Optional[str] = None
    notify_webhook: Optional[str] = None
    priority: int = 100
    is_active: bool = True


class TransferRuleCreate(TransferRuleBase):
    pass


class TransferRuleUpdate(BaseModel):
    name: Optional[str] = None
    rule_type: Optional[str] = Field(default=None, pattern="^(keyword|time|manual)$")
    condition: Optional[str] = None
    action: Optional[str] = Field(default=None, pattern="^(transfer|notify)$")
    transfer_message: Optional[str] = None
    notify_email: Optional[str] = None
    notify_webhook: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class TransferRuleResponse(TransferRuleBase):
    id: int
    tenant_id: str
    bot_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ManualTriggerRequest(BaseModel):
    rule_id: Optional[int] = None
    note: Optional[str] = None


async def _post_webhook_async(url: str, payload: dict) -> None:
    if not is_safe_outbound_url(url, require_https=True):
        logger.warning("transfer_rule_webhook_blocked_unsafe_url", extra={"url": url})
        return
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        logger.warning("transfer_rule_webhook_failed", extra={"error": str(exc)})


def _notify_rule_side_effects(
    db: Session,
    tenant_id: str,
    rule: AgentTransferRuleDB,
    conversation_id: int,
    user_message: str,
):
    payload = {
        "event": "agent_transfer_rule_triggered",
        "conversation_id": conversation_id,
        "rule_id": rule.id,
        "rule_name": rule.name,
        "rule_type": rule.rule_type,
        "action": rule.action,
        "message": user_message,
    }

    if rule.notify_email:
        body = (
            f"<h3>Agent Transfer Rule Triggered</h3>"
            f"<p>Conversation: {conversation_id}</p>"
            f"<p>Rule: {rule.name} ({rule.rule_type})</p>"
            f"<p>Message: {user_message}</p>"
        )
        email_service.send_email(
            db,
            tenant_id=tenant_id,
            subject="Agent Transfer Triggered",
            body=body,
            recipient=rule.notify_email,
        )

    if rule.notify_webhook:
        asyncio.create_task(_post_webhook_async(rule.notify_webhook, payload))
    integration_service.notify_slack_event(
        db=db,
        tenant_id=tenant_id,
        bot_id=rule.bot_id,
        event_type="transfer_rule_triggered",
        title="Transfer rule triggered",
        fields={
            "Conversation ID": conversation_id,
            "Rule": rule.name,
            "Rule Type": rule.rule_type,
            "Action": rule.action,
            "User Message": user_message,
        },
    )


@router.post("/bots/{bot_id}/rules", response_model=TransferRuleResponse)
def create_rule(
    bot_id: int,
    payload: TransferRuleCreate,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    rule = AgentTransferRuleDB(
        tenant_id=tenant_id,
        bot_id=bot_id,
        **payload.model_dump(),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/bots/{bot_id}/rules", response_model=List[TransferRuleResponse])
def list_rules(
    bot_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return (
        db.query(AgentTransferRuleDB)
        .filter(AgentTransferRuleDB.bot_id == bot_id, AgentTransferRuleDB.tenant_id == tenant_id)
        .order_by(AgentTransferRuleDB.priority.asc(), AgentTransferRuleDB.id.asc())
        .all()
    )


@router.put("/bots/{bot_id}/rules/{rule_id}", response_model=TransferRuleResponse)
def update_rule(
    bot_id: int,
    rule_id: int,
    payload: TransferRuleUpdate,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    rule = (
        db.query(AgentTransferRuleDB)
        .filter(
            AgentTransferRuleDB.id == rule_id,
            AgentTransferRuleDB.bot_id == bot_id,
            AgentTransferRuleDB.tenant_id == tenant_id,
        )
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/bots/{bot_id}/rules/{rule_id}")
def delete_rule(
    bot_id: int,
    rule_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    rule = (
        db.query(AgentTransferRuleDB)
        .filter(
            AgentTransferRuleDB.id == rule_id,
            AgentTransferRuleDB.bot_id == bot_id,
            AgentTransferRuleDB.tenant_id == tenant_id,
        )
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/trigger")
def trigger_manual_transfer(
    conversation_id: int,
    payload: ManualTriggerRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    conv = (
        db.query(ConversationDB)
        .filter(ConversationDB.id == conversation_id, ConversationDB.tenant_id == tenant_id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not conv.bot_id:
        raise HTTPException(status_code=400, detail="Conversation has no associated bot")

    query = (
        db.query(AgentTransferRuleDB)
        .filter(
            AgentTransferRuleDB.tenant_id == tenant_id,
            AgentTransferRuleDB.bot_id == conv.bot_id,
            AgentTransferRuleDB.rule_type == "manual",
            AgentTransferRuleDB.is_active.is_(True),
        )
    )
    if payload.rule_id:
        query = query.filter(AgentTransferRuleDB.id == payload.rule_id)
    rule = query.order_by(AgentTransferRuleDB.priority.asc(), AgentTransferRuleDB.id.asc()).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Manual transfer rule not found")

    conv.agent_requested = True
    conv.status = "open"
    transfer_msg = rule.transfer_message or "I am connecting you with a human agent now."
    db.add(MessageDB(conversation_id=conv.id, sender="bot", text=transfer_msg))
    if payload.note:
        db.add(MessageDB(conversation_id=conv.id, sender="agent", text=f"[MANUAL NOTE] {payload.note}"))

    _notify_rule_side_effects(db, tenant_id, rule, conv.id, payload.note or "manual trigger")
    db.commit()
    return {"ok": True, "conversation_id": conv.id, "rule_id": rule.id, "status": conv.status}
