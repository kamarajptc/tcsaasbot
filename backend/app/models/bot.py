from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(255))
    prompt_template = Column(Text, default="You are a helpful assistant.")
    response_mode = Column(String(40), default="knowledge_plus_reasoning")
    welcome_message = Column(String(255), default="Welcome to TangentCloud. Ask me anything.")
    primary_color = Column(String(20), default="#2563eb")
    avatar_url = Column(String(255), nullable=True)
    position = Column(String(20), default="right") # left, right
    placeholder_text = Column(String(100), default="Type a message...")
    bubble_greeting = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    tools = Column(JSON, default=list) # JSON list of enabled tools e.g. ["search", "calculator"]
    
    # Visual Builder & Flow Configuration
    flow_data = Column(JSON, default=dict) # Flow builder nodes and connections
    enabled_flows = Column(JSON, default=list) # List of enabled flow IDs
    
    # Rich Messages Configuration
    rich_messages_enabled = Column(Boolean, default=True)
    quick_replies = Column(JSON, default=list) # Quick reply buttons
    canned_responses = Column(JSON, default=list) # Canned responses/Shortcuts
    greeting_enabled = Column(Boolean, default=True)
    greeting_message = Column(String(500), nullable=True)
    
    # AI Training & FAQ
    faq_enabled = Column(Boolean, default=True)
    custom_answers = Column(JSON, default=dict) # Custom Q&A overrides
    
    # Agent Transfer & Live Chat
    agent_transfer_enabled = Column(Boolean, default=False)
    agent_email = Column(String(255), nullable=True)
    agent_webhook = Column(String(500), nullable=True)
    transfer_trigger_keywords = Column(JSON, default=list) # Keywords that trigger transfer
    
    # Small Talk
    small_talk_enabled = Column(Boolean, default=True)
    small_talk_responses = Column(JSON, default=dict)
    
    # Data Collection
    collect_name = Column(Boolean, default=False)
    collect_email = Column(Boolean, default=False)
    collect_phone = Column(Boolean, default=False)
    collect_custom_fields = Column(JSON, default=list)
    
    # Integrations
    shopify_enabled = Column(Boolean, default=False)
    shopify_store_url = Column(String(255), nullable=True)
    slack_enabled = Column(Boolean, default=False)
    slack_webhook = Column(String(500), nullable=True)
    zendesk_enabled = Column(Boolean, default=False)
    zendesk_subdomain = Column(String(100), nullable=True)
    freshdesk_enabled = Column(Boolean, default=False)
    freshdesk_domain = Column(String(100), nullable=True)
    
    # Goals & Analytics
    goals = Column(JSON, default=list) # Track conversions, purchases, etc.
    tags = Column(JSON, default=list) # Chat tags for categorization
    
    # A/B Testing
    ab_test_enabled = Column(Boolean, default=False)
    ab_test_variants = Column(JSON, default=list)
    
    # Version Control
    flow_version = Column(Integer, default=1)
    flow_version_history = Column(JSON, default=list) # Previous flow versions
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relationship to conversations if needed
    # conversations = relationship("ConversationDB", back_populates="bot")


class BotFAQ(Base):
    """AI Training - Custom Q&A for the bot"""
    __tablename__ = "bot_faqs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    keywords = Column(JSON, default=list) # Alternative phrasings
    category = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)
    success_rate = Column(Integer, default=0) # Percentage
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)


class BotFlow(Base):
    """Visual Flow Builder - Flow definitions"""
    __tablename__ = "bot_flows"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(255))
    flow_data = Column(JSON, default=dict) # Nodes, edges, positions
    is_active = Column(Boolean, default=True)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)


class BotIntegration(Base):
    """Integration configurations"""
    __tablename__ = "bot_integrations"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=False)
    integration_type = Column(String(50), nullable=False) # shopify, slack, zendesk, etc.
    config = Column(JSON, default=dict) # Integration-specific config
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
