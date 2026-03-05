from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import asyncio
import json
import random
import time

from app.services.rag_service import rag_service
from app.services.agent_service import agent_service
from app.core.security import get_current_user_id
from app.core.database import get_db, ConversationDB, MessageDB, TenantUsageDB, AgentTransferRuleDB
from app.core.logging import logger
from app.core.usage_limits import check_message_quota
from app.models.bot import Bot, BotFlow
from app.services.email_service import email_service
from app.services.integration_service import integration_service
from langchain_core.messages import HumanMessage, AIMessage
import httpx

from app.core.url_security import is_safe_outbound_url

router = APIRouter()

def _increment_usage(db: Session, tenant_id: str, field: str):
    usage = db.query(TenantUsageDB).filter(TenantUsageDB.tenant_id == tenant_id).first()
    if not usage:
        usage = TenantUsageDB(tenant_id=tenant_id)
        db.add(usage)
    
    current_val = getattr(usage, field) or 0
    setattr(usage, field, current_val + 1)
    db.commit()

def _get_or_create_conversation(db: Session, tenant_id: str, conversation_id: Optional[int], bot_id: Optional[int]):
    if conversation_id:
        conv = db.query(ConversationDB).filter(ConversationDB.id == conversation_id, ConversationDB.tenant_id == tenant_id).first()
        if conv:
            return conv
    
    conv = ConversationDB(tenant_id=tenant_id, bot_id=bot_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    logger.info("conversation_created", extra={
        "conversation_id": conv.id, "tenant_id": tenant_id, "bot_id": bot_id
    })
    return conv

def _get_chat_history(db: Session, conversation_id: int):
    history_msgs = db.query(MessageDB).filter(MessageDB.conversation_id == conversation_id).order_by(MessageDB.created_at.desc()).limit(11).all()
    history_msgs.reverse()
    chat_history = []
    for m in history_msgs:
        if m.sender == 'user':
            chat_history.append(HumanMessage(content=m.text))
        else:
            chat_history.append(AIMessage(content=m.text))
    return chat_history

TRANSFER_KEYWORDS = ["talk to human", "speak to agent", "representative", "human help"]

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    bot_id: Optional[int] = None

class MessageResponse(BaseModel):
    id: int
    sender: str
    text: str
    created_at: datetime
    sources: Optional[List[Dict]] = None

class ActionButton(BaseModel):
    label: str
    value: str

class ChatResponse(BaseModel):
    answer: str
    conversation_id: int
    sources: List[Dict]
    actions: Optional[List[ActionButton]] = None
    agent_requested: Optional[bool] = False


def _build_capacity_fallback_message() -> str:
    return (
        "I am temporarily at capacity right now. "
        "Please try again in a minute, or contact support if this keeps happening."
    )


def _sanitize_answer_text(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if not text:
        return text
    if len(text) > 900:
        text = text[:900].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."
    if text[-1] not in ".!?":
        text += "."
    return text


def _sanitize_sources(sources: List[Dict]) -> List[Dict]:
    cleaned = []
    seen = set()
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        item = {
            "doc_id": src.get("doc_id"),
            "title": src.get("title"),
            "source": src.get("source"),
            "content_type": src.get("content_type", "page"),
            "section_key": src.get("section_key"),
            "section_kind": src.get("section_kind"),
        }
        key = (item["doc_id"], item["source"], item["section_key"])
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned[:5]


def _build_ledger_fallback(question: str, tenant_id: str, bot: Optional[Bot] = None):
    try:
        fallback = rag_service.answer_from_knowledge_ledger(
            question=question,
            collection_name=tenant_id,
            k=5,
            bot_instructions=((bot.prompt_template if bot else None) or "").strip(),
            bot_name=(bot.name if bot else None),
        )
        answer = _sanitize_answer_text(fallback.get("answer") or _build_capacity_fallback_message())
        sources = _sanitize_sources(fallback.get("sources") or [])
        return answer, sources
    except Exception as e:
        logger.error("ledger_fallback_failed", extra={
            "tenant_id": tenant_id,
            "error": str(e),
        })
        return _build_capacity_fallback_message(), []

def _check_agent_transfer(message: str, bot: Optional[Bot], conv, db: Session) -> Optional[dict]:
    """Check if the message triggers an agent transfer. Returns a response dict or None."""
    if not bot or not bot.agent_transfer_enabled:
        return None
    if not any(kw in message.lower() for kw in TRANSFER_KEYWORDS):
        return None
    conv.agent_requested = True
    conv.status = "open"
    transfer_msg = "I'm connecting you with a human agent who can help you better. Please wait a moment."
    db.add(MessageDB(conversation_id=conv.id, sender='bot', text=transfer_msg))
    db.commit()
    integration_service.notify_slack_event(
        db=db,
        tenant_id=bot.tenant_id,
        bot_id=bot.id,
        event_type="transfer_triggered",
        title="Agent transfer requested",
        fields={
            "Conversation ID": conv.id,
            "Trigger": "keyword",
            "User Message": message,
        },
    )
    logger.info("agent_transfer_triggered", extra={
        "conversation_id": conv.id, "bot_id": bot.id, "tenant_id": bot.tenant_id
    })
    return {"answer": transfer_msg, "conversation_id": conv.id, "sources": [], "actions": []}


def _rule_matches(rule: AgentTransferRuleDB, message: str, conv) -> bool:
    msg_lower = (message or "").lower()
    if rule.rule_type == "keyword":
        keywords = [k.strip().lower() for k in (rule.condition or "").split(",") if k.strip()]
        return any(k in msg_lower for k in keywords)
    if rule.rule_type == "time":
        try:
            minutes = int((rule.condition or "0").strip())
        except ValueError:
            return False
        if minutes <= 0:
            return False
        age_minutes = (datetime.now(timezone.utc).replace(tzinfo=None) - conv.created_at).total_seconds() / 60.0
        return age_minutes >= minutes
    return False


async def _post_webhook_async(url: str, payload: dict) -> None:
    if not is_safe_outbound_url(url, require_https=True):
        logger.warning("transfer_rule_webhook_blocked_unsafe_url", extra={"url": url})
        return
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        logger.warning("transfer_rule_webhook_failed", extra={"error": str(exc)})


def _spawn_background(coro) -> None:
    try:
        asyncio.create_task(coro)
    except RuntimeError:
        logger.warning("background_task_spawn_failed")


def _notify_transfer_side_effects(rule: AgentTransferRuleDB, tenant_id: str, conv, user_message: str, db: Session):
    if rule.notify_email:
        body = (
            f"<h3>Transfer Rule Triggered</h3>"
            f"<p>Conversation: {conv.id}</p>"
            f"<p>Rule: {rule.name} ({rule.rule_type})</p>"
            f"<p>User message: {user_message}</p>"
        )
        email_service.send_email(
            db=db,
            tenant_id=tenant_id,
            subject="Transfer Rule Triggered",
            body=body,
            recipient=rule.notify_email,
        )
    if rule.notify_webhook:
        _spawn_background(_post_webhook_async(
            rule.notify_webhook,
            {
                "event": "transfer_rule_triggered",
                "conversation_id": conv.id,
                "tenant_id": tenant_id,
                "rule_id": rule.id,
                "rule_name": rule.name,
                "message": user_message,
            },
        ))
    integration_service.notify_slack_event(
        db=db,
        tenant_id=tenant_id,
        bot_id=rule.bot_id,
        event_type="transfer_rule_triggered",
        title="Transfer rule triggered",
        fields={
            "Conversation ID": conv.id,
            "Rule": rule.name,
            "Rule Type": rule.rule_type,
            "Action": rule.action,
            "User Message": user_message,
        },
    )


def _check_transfer_rules(message: str, bot: Optional[Bot], conv, db: Session, tenant_id: str) -> Optional[dict]:
    if not bot:
        return None
    rules = (
        db.query(AgentTransferRuleDB)
        .filter(
            AgentTransferRuleDB.tenant_id == tenant_id,
            AgentTransferRuleDB.bot_id == bot.id,
            AgentTransferRuleDB.is_active.is_(True),
        )
        .order_by(AgentTransferRuleDB.priority.asc(), AgentTransferRuleDB.id.asc())
        .all()
    )
    if not rules:
        return None

    for rule in rules:
        if rule.rule_type == "manual":
            continue
        if not _rule_matches(rule, message, conv):
            continue

        _notify_transfer_side_effects(rule, tenant_id, conv, message, db)
        if rule.action == "notify":
            logger.info("transfer_rule_notify_only", extra={
                "tenant_id": tenant_id,
                "conversation_id": conv.id,
                "bot_id": bot.id,
                "rule_id": rule.id,
            })
            continue

        conv.agent_requested = True
        conv.status = "open"
        transfer_msg = (
            (rule.transfer_message or "").strip()
            or "I'm connecting you with a human agent who can help you better. Please wait a moment."
        )
        db.add(MessageDB(conversation_id=conv.id, sender="bot", text=transfer_msg))
        db.commit()
        logger.info("transfer_rule_triggered", extra={
            "tenant_id": tenant_id,
            "conversation_id": conv.id,
            "bot_id": bot.id,
            "rule_id": rule.id,
            "rule_type": rule.rule_type,
        })
        return {"answer": transfer_msg, "conversation_id": conv.id, "sources": [], "actions": []}

    return None


def _parse_json_list(value) -> List:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _collect_active_flow_nodes(db: Session, bot: Optional[Bot]) -> List[Dict]:
    if not bot:
        return []
    nodes: List[Dict] = []

    flow_data = bot.flow_data if isinstance(bot.flow_data, dict) else {}
    if flow_data:
        nodes.extend(flow_data.get("nodes") or [])

    enabled_flow_ids = _parse_json_list(bot.enabled_flows)
    enabled_flow_ids = [fid for fid in enabled_flow_ids if isinstance(fid, int)]
    if enabled_flow_ids:
        active_flows = (
            db.query(BotFlow)
            .filter(
                BotFlow.bot_id == bot.id,
                BotFlow.id.in_(enabled_flow_ids),
                BotFlow.is_active.is_(True),
            )
            .all()
        )
        for flow in active_flows:
            data = flow.flow_data if isinstance(flow.flow_data, dict) else {}
            nodes.extend(data.get("nodes") or [])

    return [node for node in nodes if isinstance(node, dict)]


def _check_flow_runtime(message: str, bot: Optional[Bot], conv, db: Session, tenant_id: str) -> Optional[dict]:
    nodes = _collect_active_flow_nodes(db, bot)
    if not nodes:
        return None

    msg_lower = (message or "").lower()
    for node in nodes:
        data = node.get("data") or {}
        if not isinstance(data, dict):
            continue
        if data.get("is_active") is False:
            continue

        response_text = (
            data.get("message")
            or data.get("response")
            or data.get("text")
            or ""
        ).strip()
        if not response_text:
            continue

        raw_keywords = (
            data.get("keywords")
            or data.get("trigger_keywords")
            or data.get("triggers")
            or data.get("trigger")
            or []
        )
        if isinstance(raw_keywords, str):
            keywords = [k.strip().lower() for k in raw_keywords.split(",") if k.strip()]
        else:
            keywords = [str(k).strip().lower() for k in (raw_keywords or []) if str(k).strip()]
        if not keywords:
            continue
        if not any(keyword in msg_lower for keyword in keywords):
            continue

        db.add(MessageDB(conversation_id=conv.id, sender="bot", text=response_text))
        _increment_usage(db, tenant_id, "messages_sent")
        db.commit()
        logger.info("flow_runtime_node_matched", extra={
            "tenant_id": tenant_id,
            "bot_id": bot.id if bot else None,
            "conversation_id": conv.id,
            "node_id": node.get("id"),
            "keywords": keywords[:5],
        })
        return {
            "answer": response_text,
            "conversation_id": conv.id,
            "sources": [],
            "actions": _get_bot_actions(bot),
        }

    logger.info("flow_runtime_evaluated_no_match", extra={
        "tenant_id": tenant_id,
        "bot_id": bot.id if bot else None,
        "conversation_id": conv.id,
        "node_count": len(nodes),
    })
    return None


def _check_small_talk(message: str, bot: Optional[Bot], conv, db: Session) -> Optional[dict]:
    """Check if the message matches a small talk trigger. Returns a response dict or None."""
    if not bot or not bot.small_talk_responses:
        return None
    responses = bot.small_talk_responses if isinstance(bot.small_talk_responses, list) else json.loads(bot.small_talk_responses)
    msg_lower = message.lower()
    for entry in responses:
        trigger = entry.get('trigger')
        if not entry.get('enabled') or not trigger:
            continue
        if trigger.lower() not in msg_lower:
            continue
        ans = entry.get('response', '')
        if entry.get('variations'):
            ans = random.choice([ans] + entry.get('variations'))
        db.add(MessageDB(conversation_id=conv.id, sender='bot', text=ans))
        db.commit()
        logger.info("small_talk_matched", extra={
            "conversation_id": conv.id, "trigger": trigger, "bot_id": bot.id
        })
        return {"answer": ans, "conversation_id": conv.id, "sources": [], "actions": bot.quick_replies or []}
    return None

async def _get_ai_response(message: str, bot: Optional[Bot], conv, db: Session, tenant_id: str):
    """Generate an AI response using either the agent service or RAG."""
    start = time.perf_counter()
    response_mode = ((bot.response_mode if bot else None) or "knowledge_plus_reasoning").strip().lower()
    tools = bot.tools if bot else None
    response_type = "agent" if (tools and tools != "[]") else "rag"

    if response_mode == "knowledge_only":
        fallback = await asyncio.to_thread(
            rag_service.answer_from_knowledge_ledger,
            question=message,
            collection_name=tenant_id,
            k=5,
            bot_instructions=((bot.prompt_template if bot else None) or "").strip(),
            bot_name=(bot.name if bot else None),
        )
        answer, sources = fallback.get("answer", ""), fallback.get("sources", [])
    elif response_type == "agent":
        tool_list = json.loads(tools) if isinstance(tools, str) else tools
        answer = await agent_service.run_agent(message, tool_list, (bot.prompt_template if bot else None) or "You are a helpful assistant.")
        sources = []
    else:
        chat_history = _get_chat_history(db, conv.id)
        response = await asyncio.to_thread(
            rag_service.query,
            message,
            collection_name=tenant_id,
            chat_history=chat_history,
            bot_instructions=((bot.prompt_template if bot else None) or "").strip(),
            bot_name=(bot.name if bot else None),
        )
        answer, sources = response['answer'], response.get('sources', [])

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    db.add(MessageDB(conversation_id=conv.id, sender='bot', text=answer))
    _increment_usage(db, tenant_id, "messages_sent")
    db.commit()

    logger.info("ai_response_generated", extra={
        "conversation_id": conv.id,
        "tenant_id": tenant_id,
        "bot_id": bot.id if bot else None,
        "response_type": response_type,
        "duration_ms": duration_ms,
        "answer_length": len(answer),
        "source_count": len(sources),
    })
    return answer, sources

def _get_bot_actions(bot: Optional[Bot]) -> list:
    """Get quick reply actions from a bot, handling both JSON and list types."""
    actions = bot.quick_replies if bot else []
    if isinstance(actions, str):
        actions = json.loads(actions)
    return actions or []

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest, 
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    conv = None
    bot = None
    try:
        logger.info("chat_request_received", extra={
            "tenant_id": tenant_id, "bot_id": request.bot_id,
            "conversation_id": request.conversation_id, "message_length": len(request.message)
        })
        check_message_quota(db, tenant_id, amount=1)
        if request.bot_id:
            bot = db.query(Bot).filter(Bot.id == request.bot_id, Bot.tenant_id == tenant_id).first()
            if not bot:
                raise HTTPException(status_code=404, detail="Bot not found")

        conv = _get_or_create_conversation(db, tenant_id, request.conversation_id, request.bot_id)
        db.add(MessageDB(conversation_id=conv.id, sender='user', text=request.message))
        
        transfer_result = _check_agent_transfer(request.message, bot, conv, db)
        if transfer_result:
            return transfer_result

        rules_result = _check_transfer_rules(request.message, bot, conv, db, tenant_id)
        if rules_result:
            return rules_result

        flow_result = _check_flow_runtime(request.message, bot, conv, db, tenant_id)
        if flow_result:
            return flow_result

        small_talk_result = _check_small_talk(request.message, bot, conv, db)
        if small_talk_result:
            return small_talk_result

        try:
            answer, sources = await _get_ai_response(request.message, bot, conv, db, tenant_id)
        except Exception as ai_error:
            logger.warning("chat_ai_primary_failed_fallback_to_ledger", extra={
                "tenant_id": tenant_id,
                "bot_id": request.bot_id,
                "conversation_id": conv.id if conv else None,
                "error": str(ai_error),
            })
            fallback_message, fallback_sources = _build_ledger_fallback(request.message, tenant_id, bot)
            db.add(MessageDB(conversation_id=conv.id, sender='bot', text=fallback_message))
            _increment_usage(db, tenant_id, "messages_sent")
            db.commit()
            return {
                "answer": fallback_message,
                "conversation_id": conv.id,
                "sources": fallback_sources,
                "actions": _get_bot_actions(bot),
            }
        return {
            "answer": _sanitize_answer_text(answer),
            "conversation_id": conv.id,
            "sources": _sanitize_sources(sources),
            "actions": _get_bot_actions(bot),
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error("chat_error", extra={
            "tenant_id": tenant_id, "bot_id": request.bot_id,
            "conversation_id": request.conversation_id, "error": error_msg
        })
        db.rollback()
        
        if "429" in error_msg or "ResourceExhausted" in error_msg or "quota" in error_msg.lower():
            fallback_message, fallback_sources = _build_ledger_fallback(request.message, tenant_id, bot)
            if conv:
                db.add(MessageDB(conversation_id=conv.id, sender='bot', text=fallback_message))
                db.commit()
                return {
                    "answer": fallback_message,
                    "conversation_id": conv.id,
                    "sources": fallback_sources,
                    "actions": _get_bot_actions(bot)
                }
            raise HTTPException(
                status_code=200,
                detail=fallback_message,
            )
            
        raise HTTPException(status_code=500, detail="Internal AI error. Please try again.")

@router.post("/public", response_model=ChatResponse)
async def chat_public(request: ChatRequest, db: Session = Depends(get_db)):
    conv = None
    bot = None
    try:
        logger.info("chat_public_request", extra={
            "bot_id": request.bot_id, "conversation_id": request.conversation_id,
            "message_length": len(request.message)
        })
        if not request.bot_id:
            raise HTTPException(status_code=400, detail="Bot ID required")
        bot = db.query(Bot).filter(Bot.id == request.bot_id, Bot.is_active == True).first()
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        check_message_quota(db, bot.tenant_id, amount=1)
        
        conv = _get_or_create_conversation(db, bot.tenant_id, request.conversation_id, request.bot_id)
        db.add(MessageDB(conversation_id=conv.id, sender='user', text=request.message))
        
        transfer_result = _check_agent_transfer(request.message, bot, conv, db)
        if transfer_result:
            return transfer_result

        rules_result = _check_transfer_rules(request.message, bot, conv, db, bot.tenant_id)
        if rules_result:
            return rules_result

        flow_result = _check_flow_runtime(request.message, bot, conv, db, bot.tenant_id)
        if flow_result:
            return flow_result

        small_talk_result = _check_small_talk(request.message, bot, conv, db)
        if small_talk_result:
            return small_talk_result

        try:
            answer, sources = await _get_ai_response(request.message, bot, conv, db, bot.tenant_id)
        except Exception as ai_error:
            logger.warning("chat_public_ai_primary_failed_fallback_to_ledger", extra={
                "tenant_id": bot.tenant_id if bot else None,
                "bot_id": request.bot_id,
                "conversation_id": conv.id if conv else None,
                "error": str(ai_error),
            })
            fallback_message, fallback_sources = _build_ledger_fallback(
                request.message,
                bot.tenant_id if bot else "default",
                bot,
            )
            db.add(MessageDB(conversation_id=conv.id, sender='bot', text=fallback_message))
            _increment_usage(db, bot.tenant_id if bot else "default", "messages_sent")
            db.commit()
            return {
                "answer": fallback_message,
                "conversation_id": conv.id,
                "sources": fallback_sources,
                "actions": _get_bot_actions(bot),
            }
        return {
            "answer": _sanitize_answer_text(answer),
            "conversation_id": conv.id,
            "sources": _sanitize_sources(sources),
            "actions": _get_bot_actions(bot),
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error("chat_public_error", extra={
            "bot_id": request.bot_id, "error": error_msg
        })
        db.rollback()
        if "429" in error_msg or "ResourceExhausted" in error_msg or "quota" in error_msg.lower():
            fallback_message, fallback_sources = _build_ledger_fallback(
                request.message,
                bot.tenant_id if bot else "default",
                bot,
            )
            if conv:
                db.add(MessageDB(conversation_id=conv.id, sender='bot', text=fallback_message))
                db.commit()
                return {
                    "answer": fallback_message,
                    "conversation_id": conv.id,
                    "sources": fallback_sources,
                    "actions": _get_bot_actions(bot)
                }
            raise HTTPException(status_code=200, detail=fallback_message)
        raise HTTPException(status_code=500, detail=error_msg)

@router.get("/public/history", response_model=List[MessageResponse])
async def get_history_public(
    conversation_id: int,
    bot_id: int,
    db: Session = Depends(get_db)
):
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.is_active == True).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    conv = (
        db.query(ConversationDB)
        .filter(
            ConversationDB.id == conversation_id,
            ConversationDB.bot_id == bot_id,
            ConversationDB.tenant_id == bot.tenant_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = db.query(MessageDB).filter(MessageDB.conversation_id == conversation_id).order_by(MessageDB.created_at.asc()).all()
    return messages

@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def add_agent_message(
    conversation_id: int,
    request: ChatRequest,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    conv = db.query(ConversationDB).filter(ConversationDB.id == conversation_id, ConversationDB.tenant_id == tenant_id).first()
    if not conv:
        logger.warning("agent_message_conversation_not_found", extra={
            "conversation_id": conversation_id, "tenant_id": tenant_id
        })
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    db_msg = MessageDB(
        conversation_id=conversation_id,
        sender='agent',
        agent_id=tenant_id,
        text=request.message,
    )
    db.add(db_msg)
    
    # Update conversation status if it was open
    if conv.status == "open":
        conv.status = "pending"
        
    db.commit()
    db.refresh(db_msg)
    logger.info("agent_message_sent", extra={
        "conversation_id": conversation_id, "tenant_id": tenant_id,
        "message_length": len(request.message)
    })
    return db_msg

@router.get("/history", response_model=List[MessageResponse])
async def get_history(
    conversation_id: Optional[int] = None,
    bot_id: Optional[int] = None,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    if not conversation_id:
        query = db.query(ConversationDB).filter(ConversationDB.tenant_id == tenant_id)
        if bot_id:
            query = query.filter(ConversationDB.bot_id == bot_id)
        last_conv = query.order_by(ConversationDB.created_at.desc()).first()
        if not last_conv: return []
        conversation_id = last_conv.id
    
    conv = db.query(ConversationDB).filter(ConversationDB.id == conversation_id, ConversationDB.tenant_id == tenant_id).first()
    if not conv: return []

    messages = db.query(MessageDB).filter(MessageDB.conversation_id == conversation_id).order_by(MessageDB.created_at.asc()).all()
    return messages
