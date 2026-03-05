import sys
import os

# Add the parent directory to sys.path so we can import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import asyncio
from app.services.rag_service import rag_service

async def seed_data():
    print("Ingesting initial data...")
    
    tenant_id = "demo-tenant-key"
    
    # 1. Ingest information about TangentCloud AI Bots itself
    about_text = """
    TangentCloud AI Bots is an innovative SaaS chatbot platform built with React Native, FastAPI, OpenAI, and Qdrant.
    It features a multi-tenant architecture where each user's data is isolated using API keys.
    The backend uses LangChain for RAG (Retrieval-Augmented Generation) to provide accurate answers from ingested documents.
    The mobile app is built with Expo and React Native, supporting both iOS and Android.
    Key features include:
    - Real-time chat with AI
    - Document ingestion (PDF, Text)
    - Source citation for transparency
    - Secure tenant isolation
    """
    
    rag_service.ingest_text(
        text=about_text, 
        metadata={"source": "system-manifest", "title": "About TangentCloud AI Bots"}, 
        collection_name=tenant_id
    )
    
    # 2. Ingest some "Help" content
    help_text = """
    How to use TangentCloud AI Bots:
    1. Send a message to the bot to start chatting.
    2. To add knowledge, use the /ingest API endpoint (or future dashboard).
    3. The bot will use your private knowledge base to answer questions.
    
    Pricing:
    - Free Tier: 100 queries/month
    - Pro Tier: Unlimited queries, $29/month
    """
    
    rag_service.ingest_text(
        text=help_text, 
        metadata={"source": "user-guide", "title": "Help & Pricing"}, 
        collection_name=tenant_id
    )
    
    print(f"Successfully ingested data for tenant: {tenant_id}")

if __name__ == "__main__":
    asyncio.run(seed_data())
