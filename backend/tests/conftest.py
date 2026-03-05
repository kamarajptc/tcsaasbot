import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set dummy API keys before importing app to avoid startup errors
os.environ["GOOGLE_API_KEY"] = "dummy_key"
os.environ["OPENAI_API_KEY"] = "dummy_key"
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["ALLOW_API_KEY_AUTH"] = "false"
os.environ["AUTH_PASSWORD"] = "password123"
os.environ["AUTH_REQUIRE_EXISTING_TENANT"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Mock telemetry to avoid OTEL errors and threading issues
import sys
from unittest.mock import MagicMock
sys.modules["app.core.telemetry"] = MagicMock()

from app.main import app
from app.core.database import Base, get_db

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    """Create a TestClient that uses the test database."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    app.state.rate_limit_session_factory = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    if hasattr(app.state, "rate_limit_session_factory"):
        delattr(app.state, "rate_limit_session_factory")
