from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    tenant_id: Optional[str] = None
    role: str = "admin"

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

async def get_current_user_context(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme)
):
    # Try X-API-Key first (for server-to-server or testing)
    api_key = request.headers.get("x-api-key")
    if settings.ALLOW_API_KEY_AUTH and api_key:
        return {"tenant_id": api_key, "role": "admin"}

    # Fallback to JWT Bearer Token
    if not token:
        logger.warning("auth_missing_credentials", extra={
            "path": request.url.path,
            "method": request.method,
            "client": request.client.host if request.client else None,
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required (X-API-Key or Bearer Token)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
        username: str = payload.get("tenant_id") or payload.get("sub")
        if username is None:
            logger.warning("auth_invalid_token_payload", extra={
                "path": request.url.path,
                "method": request.method,
            })
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return {"tenant_id": username, "role": payload.get("role", "admin")}
    except JWTError:
        logger.warning("auth_invalid_token", extra={
            "path": request.url.path,
            "method": request.method,
        })
        raise HTTPException(status_code=401, detail="Could not validate credentials")


async def get_current_user_id(
    context: dict = Depends(get_current_user_context),
):
    return context["tenant_id"]
