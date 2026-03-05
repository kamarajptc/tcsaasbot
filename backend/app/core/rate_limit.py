from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from typing import Deque

import redis.asyncio as redis
from jose import jwt
from sqlalchemy import func
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import (
    SessionLocal,
    TenantDB,
    RateLimitPolicyDB,
    RateLimitEventDB,
    TenantAlertSettingsDB,
    RateLimitAlertDeliveryDB,
)
from app.core.logging import logger
from app.services.email_service import email_service
from app.services.integration_service import integration_service


class _LocalWindowRateLimiter:
    def __init__(self):
        self._events: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time.time()
        cutoff = now - window_seconds
        async with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            allowed = len(bucket) < limit
            if allowed:
                bucket.append(now)
            remaining = max(0, limit - len(bucket))
            retry_after = 0
            if bucket and not allowed:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
            return allowed, remaining, retry_after


class _RedisWindowRateLimiter:
    def __init__(self, redis_url: str):
        self.client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        pipe = self.client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = await pipe.execute()
        if count == 1:
            await self.client.expire(key, window_seconds)
            ttl = window_seconds
        allowed = count <= limit
        remaining = max(0, limit - count)
        retry_after = 0 if allowed else max(1, ttl if ttl and ttl > 0 else window_seconds)
        return allowed, remaining, retry_after


_local_limiter = _LocalWindowRateLimiter()
_redis_limiter: _RedisWindowRateLimiter | None = None
_redis_lock = asyncio.Lock()
_redis_disabled = False
_policy_cache: dict[str, tuple[float, dict[str, str | int]]] = {}


def _now_ts() -> float:
    return time.time()


def clear_rate_limit_policy_cache(tenant_id: str | None = None) -> None:
    if tenant_id is None:
        _policy_cache.clear()
        return
    prefix = f"{tenant_id}:"
    for key in [cache_key for cache_key in _policy_cache if cache_key.startswith(prefix)]:
        _policy_cache.pop(key, None)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _get_redis_limiter() -> _RedisWindowRateLimiter | None:
    global _redis_limiter, _redis_disabled
    if _redis_disabled:
        return None
    if _redis_limiter is not None:
        return _redis_limiter

    settings = get_settings()
    async with _redis_lock:
        if _redis_limiter is not None:
            return _redis_limiter
        try:
            limiter = _RedisWindowRateLimiter(settings.REDIS_URL)
            await limiter.client.ping()
            _redis_limiter = limiter
            logger.info("rate_limit_backend_ready", extra={"backend": "redis"})
            return _redis_limiter
        except Exception as exc:
            _redis_disabled = True
            logger.warning("rate_limit_backend_fallback_local", extra={"error": str(exc)})
            return None


def _tenant_rate_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key")
    if api_key:
        return f"tenant:{api_key}"

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        try:
            claims = jwt.get_unverified_claims(token)
            tenant_id = claims.get("tenant_id") or claims.get("sub")
            if tenant_id:
                return f"tenant:{tenant_id}"
        except Exception:
            pass
        return f"bearer:{hash(token)}"

    client = request.client.host if request.client else "unknown"
    return f"ip:{client}"


def _path_bucket(path: str) -> str:
    if path.startswith("/api/v1/chat/public"):
        return "chat_public"
    if path.startswith("/api/v1/chat/"):
        return "chat"
    if path.startswith("/api/v1/ingest/scrape"):
        return "ingest_scrape"
    if path.startswith("/api/v1/auth/"):
        return "auth"
    if path.startswith("/api/v1/dashboard/conversations"):
        return "dashboard_conversations"
    return "default"


def _default_limit_for_bucket(bucket: str) -> int:
    settings = get_settings()
    if bucket == "chat_public":
        return settings.RATE_LIMIT_PUBLIC_CHAT_RPM
    if bucket == "auth":
        return settings.RATE_LIMIT_AUTH_RPM
    return settings.RATE_LIMIT_DEFAULT_RPM


def get_effective_rate_limits_sync(tenant_id: str, session_factory=None) -> dict[str, int]:
    session = session_factory() if session_factory else SessionLocal()
    try:
        tenant = session.query(TenantDB).filter(TenantDB.id == tenant_id).first()
        plan = str(tenant.plan).lower() if tenant and tenant.plan else "starter"
        rows = (
            session.query(RateLimitPolicyDB)
            .filter(
                RateLimitPolicyDB.is_active.is_(True),
                (
                    (RateLimitPolicyDB.tenant_id == tenant_id)
                    | ((RateLimitPolicyDB.tenant_id.is_(None)) & (RateLimitPolicyDB.plan == plan))
                ),
            )
            .order_by(RateLimitPolicyDB.id.asc())
            .all()
        )
        effective: dict[str, int] = {}
        for row in rows:
            current = effective.get(row.route_key)
            if row.tenant_id == tenant_id or current is None:
                effective[row.route_key] = int(row.rpm_limit)
        return effective
    finally:
        if not session_factory:
            session.close()


def _resolve_policy_sync(tenant_id: str | None, bucket: str, session_factory=None) -> dict[str, str | int]:
    settings = get_settings()
    cache_key = f"{tenant_id or 'anonymous'}:{bucket}"
    cached = _policy_cache.get(cache_key)
    if cached and cached[0] > _now_ts():
        return cached[1]

    session = session_factory() if session_factory else SessionLocal()
    try:
        plan = "starter"
        if tenant_id:
            tenant = session.query(TenantDB).filter(TenantDB.id == tenant_id).first()
            if tenant and tenant.plan:
                plan = str(tenant.plan).lower()

        policy = None
        if tenant_id:
            policy = (
                session.query(RateLimitPolicyDB)
                .filter(
                    RateLimitPolicyDB.tenant_id == tenant_id,
                    RateLimitPolicyDB.route_key == bucket,
                    RateLimitPolicyDB.is_active.is_(True),
                )
                .order_by(RateLimitPolicyDB.id.desc())
                .first()
            )
            if not policy:
                policy = (
                    session.query(RateLimitPolicyDB)
                    .filter(
                        RateLimitPolicyDB.tenant_id == tenant_id,
                        RateLimitPolicyDB.route_key == "default",
                        RateLimitPolicyDB.is_active.is_(True),
                    )
                    .order_by(RateLimitPolicyDB.id.desc())
                    .first()
                )
        if not policy:
            policy = (
                session.query(RateLimitPolicyDB)
                .filter(
                    RateLimitPolicyDB.tenant_id.is_(None),
                    RateLimitPolicyDB.plan == plan,
                    RateLimitPolicyDB.route_key == bucket,
                    RateLimitPolicyDB.is_active.is_(True),
                )
                .order_by(RateLimitPolicyDB.id.desc())
                .first()
            )
        if not policy:
            policy = (
                session.query(RateLimitPolicyDB)
                .filter(
                    RateLimitPolicyDB.tenant_id.is_(None),
                    RateLimitPolicyDB.plan == plan,
                    RateLimitPolicyDB.route_key == "default",
                    RateLimitPolicyDB.is_active.is_(True),
                )
                .order_by(RateLimitPolicyDB.id.desc())
                .first()
            )
        resolved = {
            "tenant_id": tenant_id or "anonymous",
            "plan": plan,
            "route_key": bucket,
            "limit": int(policy.rpm_limit) if policy else _default_limit_for_bucket(bucket),
        }
        _policy_cache[cache_key] = (_now_ts() + settings.RATE_LIMIT_POLICY_CACHE_SECONDS, resolved)
        return resolved
    finally:
        if not session_factory:
            session.close()


async def _resolve_policy(request: Request, tenant_id: str | None, bucket: str) -> dict[str, str | int]:
    session_factory = getattr(request.app.state, "rate_limit_session_factory", None)
    if session_factory:
        return _resolve_policy_sync(tenant_id, bucket, session_factory=session_factory)
    return await asyncio.to_thread(_resolve_policy_sync, tenant_id, bucket)


def _record_throttle_event_sync(policy: dict[str, str | int], path: str, limiter_key: str, retry_after: int, session_factory=None) -> None:
    session = session_factory() if session_factory else SessionLocal()
    try:
        session.add(
            RateLimitEventDB(
                tenant_id=str(policy["tenant_id"]) if policy["tenant_id"] != "anonymous" else None,
                plan=str(policy["plan"]),
                route_key=str(policy["route_key"]),
                request_path=path,
                limiter_key=limiter_key,
                limit_value=int(policy["limit"]),
                retry_after_seconds=int(retry_after),
            )
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("rate_limit_event_record_failed", extra={"error": str(exc)})
    finally:
        if not session_factory:
            session.close()


async def _record_throttle_event(request: Request, policy: dict[str, str | int], path: str, limiter_key: str, retry_after: int) -> None:
    session_factory = getattr(request.app.state, "rate_limit_session_factory", None)
    if session_factory:
        _record_throttle_event_sync(policy, path, limiter_key, retry_after, session_factory=session_factory)
        _maybe_send_rate_limit_alert_sync(policy, path, session_factory=session_factory)
        return
    await asyncio.to_thread(_record_throttle_event_sync, policy, path, limiter_key, retry_after)
    await asyncio.to_thread(_maybe_send_rate_limit_alert_sync, policy, path)


def _get_alert_settings(session, tenant_id: str) -> TenantAlertSettingsDB:
    settings = get_settings()
    row = session.query(TenantAlertSettingsDB).filter(TenantAlertSettingsDB.tenant_id == tenant_id).first()
    if row:
        return row
    return TenantAlertSettingsDB(
        tenant_id=tenant_id,
        rate_limit_email_enabled=False,
        rate_limit_email_recipient=None,
        rate_limit_webhook_enabled=False,
        rate_limit_webhook_url=None,
        rate_limit_min_hits=settings.RATE_LIMIT_ALERT_DEFAULT_MIN_HITS,
        rate_limit_window_minutes=settings.RATE_LIMIT_ALERT_DEFAULT_WINDOW_MINUTES,
        rate_limit_cooldown_minutes=settings.RATE_LIMIT_ALERT_DEFAULT_COOLDOWN_MINUTES,
    )


def _send_rate_limit_alert_email(session, tenant_id: str, recipient: str, subject: str, body: str) -> bool:
    return email_service.send_email(session, tenant_id, subject, body, recipient=recipient)


def _record_alert_delivery(session, tenant_id: str, route_key: str, channel: str, hits: int) -> None:
    row = (
        session.query(RateLimitAlertDeliveryDB)
        .filter(
            RateLimitAlertDeliveryDB.tenant_id == tenant_id,
            RateLimitAlertDeliveryDB.route_key == route_key,
            RateLimitAlertDeliveryDB.channel == channel,
        )
        .first()
    )
    if not row:
        row = RateLimitAlertDeliveryDB(
            tenant_id=tenant_id,
            route_key=route_key,
            channel=channel,
        )
        session.add(row)
    row.hits = hits
    row.last_sent_at = _utcnow_naive()
    session.commit()


def _maybe_send_rate_limit_alert_sync(policy: dict[str, str | int], path: str, session_factory=None) -> None:
    tenant_id = str(policy.get("tenant_id") or "")
    if not tenant_id or tenant_id == "anonymous":
        return

    session = session_factory() if session_factory else SessionLocal()
    try:
        alert_settings = _get_alert_settings(session, tenant_id)
        if not alert_settings.rate_limit_email_enabled and not alert_settings.rate_limit_webhook_enabled:
            return

        now = _utcnow_naive()
        window_minutes = max(1, int(alert_settings.rate_limit_window_minutes or 60))
        min_hits = max(1, int(alert_settings.rate_limit_min_hits or 5))
        cooldown_minutes = max(1, int(alert_settings.rate_limit_cooldown_minutes or 60))
        route_key = str(policy["route_key"])

        since = now - timedelta(minutes=window_minutes)
        hit_count = (
            session.query(func.count(RateLimitEventDB.id))
            .filter(
                RateLimitEventDB.tenant_id == tenant_id,
                RateLimitEventDB.route_key == route_key,
                RateLimitEventDB.exceeded_at >= since,
            )
            .scalar()
            or 0
        )
        if int(hit_count) < min_hits:
            return

        cooldown_since = now - timedelta(minutes=cooldown_minutes)
        recent_channels = {
            row.channel
            for row in session.query(RateLimitAlertDeliveryDB)
            .filter(
                RateLimitAlertDeliveryDB.tenant_id == tenant_id,
                RateLimitAlertDeliveryDB.route_key == route_key,
                RateLimitAlertDeliveryDB.last_sent_at >= cooldown_since,
            )
            .all()
        }

        subject = f"Rate limit alert: {route_key} exceeded repeatedly"
        body = (
            f"<h2>Rate limit alert</h2>"
            f"<p>Tenant <strong>{tenant_id}</strong> exceeded the <strong>{route_key}</strong> budget "
            f"<strong>{int(hit_count)}</strong> times in the last <strong>{window_minutes}</strong> minutes.</p>"
            f"<p>Latest path: <code>{path}</code></p>"
            f"<p>Current plan: <strong>{policy['plan']}</strong> | Limit: <strong>{policy['limit']} rpm</strong></p>"
        )

        if alert_settings.rate_limit_email_enabled and "email" not in recent_channels:
            recipient = (alert_settings.rate_limit_email_recipient or "").strip()
            if recipient and _send_rate_limit_alert_email(session, tenant_id, recipient, subject, body):
                _record_alert_delivery(session, tenant_id, route_key, "email", int(hit_count))

        if alert_settings.rate_limit_webhook_enabled and "webhook" not in recent_channels:
            webhook_url = (alert_settings.rate_limit_webhook_url or "").strip()
            if webhook_url:
                payload = {
                    "event_type": "rate_limit_alert",
                    "tenant_id": tenant_id,
                    "plan": policy["plan"],
                    "route_key": route_key,
                    "hits": int(hit_count),
                    "window_minutes": window_minutes,
                    "limit": int(policy["limit"]),
                    "request_path": path,
                    "support_email": get_settings().SUPPORT_EMAIL,
                }
                sent = integration_service.post_json_webhook(webhook_url, payload)
                if sent:
                    _record_alert_delivery(session, tenant_id, route_key, "webhook", int(hit_count))
    except Exception as exc:
        logger.warning("rate_limit_alert_delivery_failed", extra={"tenant_id": tenant_id, "error": str(exc)})
        session.rollback()
    finally:
        if not session_factory:
            session.close()


async def _check_limit(key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
    redis_limiter = await _get_redis_limiter()
    if redis_limiter is not None:
        try:
            return await redis_limiter.hit(key, limit, window_seconds)
        except Exception as exc:
            global _redis_limiter, _redis_disabled
            _redis_limiter = None
            _redis_disabled = True
            logger.warning("rate_limit_redis_failed_fallback_local", extra={"error": str(exc)})
    return await _local_limiter.hit(key, limit, window_seconds)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path
        if path.startswith("/docs") or path.startswith("/openapi") or path == "/healthz":
            return await call_next(request)

        bucket = _path_bucket(path)
        tenant_key = _tenant_rate_key(request)
        tenant_id = tenant_key.split("tenant:", 1)[1] if tenant_key.startswith("tenant:") else None
        policy = await _resolve_policy(request, tenant_id, bucket)
        limit = int(policy["limit"])
        key = f"rl:{tenant_key}:{bucket}:60"
        allowed, remaining, retry_after = await _check_limit(key, limit, 60)
        if not allowed:
            await _record_throttle_event(request, policy, path, key, retry_after)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "tenant_id": policy["tenant_id"],
                    "plan": policy["plan"],
                    "route_key": policy["route_key"],
                    "limit": limit,
                    "remaining": remaining,
                    "retry_after_seconds": retry_after,
                    "support": {
                        "email": settings.SUPPORT_EMAIL,
                        "url": settings.SUPPORT_URL,
                        "message": "If you need a higher limit, contact support or upgrade your plan.",
                    },
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": str(remaining),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
