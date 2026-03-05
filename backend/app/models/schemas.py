from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class BotBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    prompt_template: Optional[str] = "You are a helpful assistant."
    response_mode: Optional[str] = "knowledge_plus_reasoning"
    welcome_message: Optional[str] = "Welcome to TangentCloud. Ask me anything."
    primary_color: Optional[str] = "#2563eb"
    avatar_url: Optional[str] = None
    position: Optional[str] = "right"
    placeholder_text: Optional[str] = "Type a message..."
    bubble_greeting: Optional[str] = None
    tools: Optional[List[str]] = []
    enabled_flows: Optional[List[int]] = []
    quick_replies: Optional[List[Dict[str, Any]]] = []
    canned_responses: Optional[List[Dict[str, Any]]] = []
    small_talk_responses: Optional[Any] = []
    rich_messages_enabled: Optional[bool] = True
    greeting_enabled: Optional[bool] = True
    greeting_message: Optional[str] = None
    faq_enabled: Optional[bool] = True
    custom_answers: Optional[Dict[str, Any]] = {}
    agent_transfer_enabled: Optional[bool] = False
    agent_email: Optional[str] = None
    agent_webhook: Optional[str] = None
    transfer_trigger_keywords: Optional[List[str]] = []
    collect_name: Optional[bool] = False
    collect_email: Optional[bool] = False
    collect_phone: Optional[bool] = False
    collect_custom_fields: Optional[List[Dict[str, Any]]] = []
    goals: Optional[List[Dict[str, Any]]] = []
    tags: Optional[List[str]] = []
    ab_test_enabled: Optional[bool] = False
    ab_test_variants: Optional[List[Dict[str, Any]]] = []
    flow_version: Optional[int] = 1
    flow_version_history: Optional[List[Dict[str, Any]]] = []
    shopify_enabled: Optional[bool] = False
    shopify_store_url: Optional[str] = None
    slack_enabled: Optional[bool] = False
    slack_webhook: Optional[str] = None
    zendesk_enabled: Optional[bool] = False
    zendesk_subdomain: Optional[str] = None
    freshdesk_enabled: Optional[bool] = False
    freshdesk_domain: Optional[str] = None
    flow_data: Optional[Dict[str, Any]] = {}

class BotCreate(BotBase):
    pass

class BotUpdate(BotBase):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt_template: Optional[str] = None
    response_mode: Optional[str] = None
    welcome_message: Optional[str] = None
    primary_color: Optional[str] = None
    avatar_url: Optional[str] = None
    position: Optional[str] = None
    placeholder_text: Optional[str] = None
    bubble_greeting: Optional[str] = None
    is_active: Optional[bool] = None
    tools: Optional[List[str]] = None
    enabled_flows: Optional[List[int]] = None
    quick_replies: Optional[List[Dict[str, Any]]] = None
    canned_responses: Optional[List[Dict[str, Any]]] = None
    small_talk_responses: Optional[List[Dict[str, Any]]] = None
    rich_messages_enabled: Optional[bool] = None
    greeting_enabled: Optional[bool] = None
    greeting_message: Optional[str] = None
    faq_enabled: Optional[bool] = None
    custom_answers: Optional[Dict[str, Any]] = None
    agent_transfer_enabled: Optional[bool] = None
    agent_email: Optional[str] = None
    agent_webhook: Optional[str] = None
    transfer_trigger_keywords: Optional[List[str]] = None
    collect_name: Optional[bool] = None
    collect_email: Optional[bool] = None
    collect_phone: Optional[bool] = None
    collect_custom_fields: Optional[List[Dict[str, Any]]] = None
    goals: Optional[List[Dict[str, Any]]] = None
    tags: Optional[List[str]] = None
    ab_test_enabled: Optional[bool] = None
    ab_test_variants: Optional[List[Dict[str, Any]]] = None
    flow_version: Optional[int] = None
    flow_version_history: Optional[List[Dict[str, Any]]] = None
    shopify_enabled: Optional[bool] = None
    shopify_store_url: Optional[str] = None
    slack_enabled: Optional[bool] = None
    slack_webhook: Optional[str] = None
    zendesk_enabled: Optional[bool] = None
    zendesk_subdomain: Optional[str] = None
    freshdesk_enabled: Optional[bool] = None
    freshdesk_domain: Optional[str] = None
    flow_data: Optional[Dict[str, Any]] = None

class BotResponse(BotBase):
    id: int
    tenant_id: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class PublicBotResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    welcome_message: Optional[str] = None
    primary_color: Optional[str] = "#2563eb"
    avatar_url: Optional[str] = None
    position: Optional[str] = "right"
    placeholder_text: Optional[str] = "Type a message..."
    bubble_greeting: Optional[str] = None
    quick_replies: Optional[List[Dict[str, Any]]] = []
    is_active: bool

    class Config:
        from_attributes = True

class AnalyticsSummary(BaseModel):
    total_conversations: int
    total_messages: int
    active_bots: int
    avg_response_time: float

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender: str
    text: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class ConversationResponse(BaseModel):
    id: int
    bot_id: Optional[int]
    bot_name: Optional[str] = "Deleted Bot"
    status: str = "new"
    agent_requested: bool = False
    created_at: datetime
    last_message: Optional[str] = ""
    last_message_sender: Optional[str] = None
    message_count: int = 0
    
    class Config:
        from_attributes = True

class TenantSettings(BaseModel):
    id: str
    name: Optional[str]
    plan: str
    messages_sent: int
    documents_indexed: int
    message_limit: int
    document_limit: int
    rate_limits: Optional[Dict[str, int]] = {}
    rate_limit_summary: Optional[Dict[str, Any]] = {}
    support: Optional[Dict[str, str]] = {}

class UsageUpdate(BaseModel):
    messages_sent: int
    documents_indexed: int

class LeadFormField(BaseModel):
    name: str
    label: str
    type: str  # text, email, tel, textarea
    required: bool = True

class LeadFormCreate(BaseModel):
    bot_id: int
    title: str = "Contact Us"
    fields: List[LeadFormField]

class LeadFormResponse(LeadFormCreate):
    id: int
    tenant_id: str
    is_active: bool

class LeadSubmit(BaseModel):
    bot_id: int
    conversation_id: int
    data: Dict[str, Any]
    country: Optional[str] = None
    source: Optional[str] = "Direct"

class LeadResponse(BaseModel):
    id: int
    bot_id: int
    conversation_id: int
    data: Dict[str, Any]
    country: Optional[str] = None
    source: Optional[str] = "Direct"
    created_at: datetime

class EmailSettingsUpdate(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    sender_email: str
    is_enabled: bool
class FAQBase(BaseModel):
    question: str
    answer: str
    keywords: Optional[List[str]] = []
    category: Optional[str] = "General"
    is_active: Optional[bool] = True

class FAQCreate(FAQBase):
    pass

class FAQUpdate(FAQBase):
    question: Optional[str] = None
    answer: Optional[str] = None
    is_active: Optional[bool] = None

class FAQResponse(FAQBase):
    id: int
    bot_id: int
    usage_count: int
    success_rate: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
