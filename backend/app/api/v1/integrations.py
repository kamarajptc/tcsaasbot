from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.bot import Bot, BotIntegration
from app.services.integration_service import integration_service

router = APIRouter()


class IntegrationUpsert(BaseModel):
    integration_type: str
    config: Dict[str, Any] = {}
    is_active: bool = True


class IntegrationResponse(BaseModel):
    id: int
    bot_id: int
    integration_type: str
    config: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ShopifyOrderLookupRequest(BaseModel):
    order_name: str = Field(..., min_length=1, max_length=120)
    email: Optional[str] = None


class ShopifyOrderLookupResponse(BaseModel):
    found: bool
    order: Optional[Dict[str, Any]] = None


def _assert_bot_ownership(db: Session, bot_id: int, tenant_id: str) -> Bot:
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.get("/bots/{bot_id}/integrations", response_model=List[IntegrationResponse])
def list_integrations(
    bot_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    _assert_bot_ownership(db, bot_id, tenant_id)
    return db.query(BotIntegration).filter(BotIntegration.bot_id == bot_id).all()


@router.post("/bots/{bot_id}/integrations", response_model=IntegrationResponse)
def upsert_integration(
    bot_id: int,
    payload: IntegrationUpsert,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    _assert_bot_ownership(db, bot_id, tenant_id)

    row = (
        db.query(BotIntegration)
        .filter(
            BotIntegration.bot_id == bot_id,
            BotIntegration.integration_type == payload.integration_type,
        )
        .first()
    )
    if not row:
        row = BotIntegration(
            bot_id=bot_id,
            integration_type=payload.integration_type,
            config=payload.config,
            is_active=payload.is_active,
        )
        db.add(row)
    else:
        row.config = payload.config
        row.is_active = payload.is_active
    db.commit()
    db.refresh(row)
    return row


@router.delete("/bots/{bot_id}/integrations/{integration_type}")
def delete_integration(
    bot_id: int,
    integration_type: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    _assert_bot_ownership(db, bot_id, tenant_id)
    row = (
        db.query(BotIntegration)
        .filter(
            BotIntegration.bot_id == bot_id,
            BotIntegration.integration_type == integration_type,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/bots/{bot_id}/shopify/order-lookup", response_model=ShopifyOrderLookupResponse)
async def shopify_order_lookup(
    bot_id: int,
    payload: ShopifyOrderLookupRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_user_id),
):
    _assert_bot_ownership(db, bot_id, tenant_id)
    try:
        return await integration_service.lookup_shopify_order_async(
            db=db,
            tenant_id=tenant_id,
            bot_id=bot_id,
            order_name=payload.order_name,
            email=payload.email,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Bot not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
