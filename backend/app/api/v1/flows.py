from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import json

from app.core.database import get_db
from app.models.bot import Bot, BotFlow
from app.core.security import get_current_user_id
from app.core.logging import logger
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class FlowBase(BaseModel):
    name: str
    description: Optional[str] = None
    flow_data: dict
    is_active: bool = True

class FlowCreate(FlowBase):
    pass

class FlowResponse(FlowBase):
    id: int
    bot_id: int
    version: int
    created_at: datetime
    
    class Config:
        from_attributes = True

@router.post("/{bot_id}/flows", response_model=FlowResponse)
def create_flow(bot_id: int, flow: FlowCreate, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    # Verify bot ownership
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
        
    db_flow = BotFlow(**flow.model_dump(), bot_id=bot_id)
    db.add(db_flow)
    db.commit()
    db.refresh(db_flow)
    
    logger.info("flow_created", extra={
        "flow_id": db_flow.id, "bot_id": bot_id, "tenant_id": tenant_id
    })
    return db_flow

@router.get("/{bot_id}/flows", response_model=List[FlowResponse])
def get_flows(bot_id: int, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    # Verify bot ownership
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
        
    flows = db.query(BotFlow).filter(BotFlow.bot_id == bot_id).all()
    return flows

@router.put("/{bot_id}/flows/{flow_id}", response_model=FlowResponse)
def update_flow(bot_id: int, flow_id: int, flow_update: FlowCreate, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    # Verify bot ownership
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
        
    db_flow = db.query(BotFlow).filter(BotFlow.id == flow_id, BotFlow.bot_id == bot_id).first()
    if not db_flow:
        raise HTTPException(status_code=404, detail="Flow not found")
        
    for key, value in flow_update.model_dump().items():
        setattr(db_flow, key, value)
    
    db_flow.version += 1
    db.commit()
    db.refresh(db_flow)
    
    logger.info("flow_updated", extra={
        "flow_id": flow_id, "bot_id": bot_id, "tenant_id": tenant_id, "new_version": db_flow.version
    })
    return db_flow

@router.delete("/{bot_id}/flows/{flow_id}")
def delete_flow(bot_id: int, flow_id: int, db: Session = Depends(get_db), tenant_id: str = Depends(get_current_user_id)):
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
        
    db_flow = db.query(BotFlow).filter(BotFlow.id == flow_id, BotFlow.bot_id == bot_id).first()
    if not db_flow:
        raise HTTPException(status_code=404, detail="Flow not found")
        
    db.delete(db_flow)
    db.commit()
    logger.info("flow_deleted", extra={"flow_id": flow_id, "bot_id": bot_id, "tenant_id": tenant_id})
    return {"ok": True}
