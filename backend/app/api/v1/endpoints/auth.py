from datetime import timedelta
from typing import Any
import hmac

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.database import get_db, TenantDB

settings = get_settings()
router = APIRouter()

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    username: str
    password: str


def _validate_credentials(db: Session, username: str, password: str) -> str:
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    valid_password = hmac.compare_digest(password, settings.AUTH_PASSWORD)
    if (
        not valid_password
        and username in settings.demo_tenant_ids
        and settings.DEMO_AUTH_PASSWORD
    ):
        valid_password = hmac.compare_digest(password, settings.DEMO_AUTH_PASSWORD)
    if not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    tenant = db.query(TenantDB).filter(TenantDB.id == username).first()
    if settings.AUTH_REQUIRE_EXISTING_TENANT and not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown tenant",
        )
    return username

@router.post("/token", response_model=Token)
def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    tenant_id = _validate_credentials(db, form_data.username, form_data.password)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": tenant_id, "tenant_id": tenant_id}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }

@router.post("/login", response_model=Token)
def login_json(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    JSON body login, get an access token for future requests.
    """
    tenant_id = _validate_credentials(db, login_data.username, login_data.password)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": tenant_id, "tenant_id": tenant_id}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
