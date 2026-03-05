from typing import Any, Dict, List, Optional

import asyncio
import httpx
import requests
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.core.url_security import is_safe_outbound_url
from app.models.bot import Bot, BotIntegration


class IntegrationService:
    def _get_bot(self, db: Session, tenant_id: str, bot_id: int) -> Optional[Bot]:
        return db.query(Bot).filter(Bot.id == bot_id, Bot.tenant_id == tenant_id).first()

    def _get_integration(self, db: Session, bot_id: int, integration_type: str) -> Optional[BotIntegration]:
        return (
            db.query(BotIntegration)
            .filter(
                BotIntegration.bot_id == bot_id,
                BotIntegration.integration_type == integration_type,
            )
            .first()
        )

    def get_slack_webhook_url(self, db: Session, tenant_id: str, bot_id: int) -> Optional[str]:
        bot = self._get_bot(db, tenant_id, bot_id)
        if not bot:
            return None

        row = self._get_integration(db, bot_id, "slack")
        if row and row.is_active:
            cfg = row.config or {}
            webhook = (
                cfg.get("webhook_url")
                or cfg.get("webhookUrl")
                or cfg.get("url")
                or ""
            ).strip()
            if webhook:
                return webhook

        if bot.slack_enabled and bot.slack_webhook:
            return bot.slack_webhook.strip()

        return None

    def post_slack_webhook(self, webhook_url: str, payload: Dict[str, Any], max_attempts: int = 3) -> bool:
        if not is_safe_outbound_url(webhook_url, require_https=True):
            logger.warning("slack_webhook_blocked_unsafe_url")
            return False
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.post(webhook_url, json=payload, timeout=4)
                if 200 <= resp.status_code < 300:
                    return True
                logger.warning(
                    "slack_webhook_non_success",
                    extra={
                        "status_code": resp.status_code,
                        "attempt": attempt,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "slack_webhook_request_failed",
                    extra={
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
        return False

    async def post_slack_webhook_async(self, webhook_url: str, payload: Dict[str, Any], max_attempts: int = 3) -> bool:
        if not is_safe_outbound_url(webhook_url, require_https=True):
            logger.warning("slack_webhook_blocked_unsafe_url")
            return False
        async with httpx.AsyncClient(timeout=4.0) as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await client.post(webhook_url, json=payload)
                    if 200 <= resp.status_code < 300:
                        return True
                    logger.warning(
                        "slack_webhook_non_success",
                        extra={"status_code": resp.status_code, "attempt": attempt},
                    )
                except Exception as exc:
                    logger.warning(
                        "slack_webhook_request_failed",
                        extra={"attempt": attempt, "error": str(exc)},
                    )
        return False

    async def post_json_webhook_async(self, webhook_url: str, payload: Dict[str, Any], max_attempts: int = 3) -> bool:
        if not is_safe_outbound_url(webhook_url, require_https=True):
            logger.warning("generic_webhook_blocked_unsafe_url")
            return False
        async with httpx.AsyncClient(timeout=4.0) as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await client.post(webhook_url, json=payload)
                    if 200 <= resp.status_code < 300:
                        return True
                    logger.warning(
                        "generic_webhook_non_success",
                        extra={"status_code": resp.status_code, "attempt": attempt},
                    )
                except Exception as exc:
                    logger.warning(
                        "generic_webhook_request_failed",
                        extra={"attempt": attempt, "error": str(exc)},
                    )
        return False

    def post_json_webhook(self, webhook_url: str, payload: Dict[str, Any], max_attempts: int = 3) -> bool:
        if not is_safe_outbound_url(webhook_url, require_https=True):
            logger.warning("generic_webhook_blocked_unsafe_url")
            return False
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.post(webhook_url, json=payload, timeout=4)
                if 200 <= resp.status_code < 300:
                    return True
                logger.warning(
                    "generic_webhook_non_success",
                    extra={"status_code": resp.status_code, "attempt": attempt},
                )
            except Exception as exc:
                logger.warning(
                    "generic_webhook_request_failed",
                    extra={"attempt": attempt, "error": str(exc)},
                )
        return False

    def notify_slack_event(
        self,
        db: Session,
        tenant_id: str,
        bot_id: int,
        event_type: str,
        title: str,
        fields: Optional[Dict[str, Any]] = None,
    ) -> bool:
        webhook_url = self.get_slack_webhook_url(db, tenant_id, bot_id)
        if not webhook_url:
            return False

        rows: List[Dict[str, str]] = []
        for key, value in (fields or {}).items():
            if value is None:
                continue
            rows.append({"type": "mrkdwn", "text": f"*{key}:* {value}"})

        payload: Dict[str, Any] = {
            "text": f"[{event_type}] {title}",
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*"}},
            ],
        }
        if rows:
            payload["blocks"].append({"type": "section", "fields": rows[:10]})

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.post_slack_webhook_async(webhook_url, payload))
            return True
        except RuntimeError:
            ok = self.post_slack_webhook(webhook_url, payload)
            if not ok:
                logger.warning(
                    "slack_event_delivery_failed",
                    extra={
                        "tenant_id": tenant_id,
                        "bot_id": bot_id,
                        "event_type": event_type,
                    },
                )
            return ok

    async def notify_slack_event_async(
        self,
        db: Session,
        tenant_id: str,
        bot_id: int,
        event_type: str,
        title: str,
        fields: Optional[Dict[str, Any]] = None,
    ) -> bool:
        webhook_url = self.get_slack_webhook_url(db, tenant_id, bot_id)
        if not webhook_url:
            return False

        rows: List[Dict[str, str]] = []
        for key, value in (fields or {}).items():
            if value is None:
                continue
            rows.append({"type": "mrkdwn", "text": f"*{key}:* {value}"})

        payload: Dict[str, Any] = {
            "text": f"[{event_type}] {title}",
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*"}},
            ],
        }
        if rows:
            payload["blocks"].append({"type": "section", "fields": rows[:10]})

        ok = await self.post_slack_webhook_async(webhook_url, payload)
        if not ok:
            logger.warning(
                "slack_event_delivery_failed",
                extra={"tenant_id": tenant_id, "bot_id": bot_id, "event_type": event_type},
            )
        return ok

    def lookup_shopify_order(
        self,
        db: Session,
        tenant_id: str,
        bot_id: int,
        order_name: str,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        bot = self._get_bot(db, tenant_id, bot_id)
        if not bot:
            raise ValueError("Bot not found")

        row = self._get_integration(db, bot_id, "shopify")
        if not row or not row.is_active:
            raise RuntimeError("Shopify integration is not active")

        cfg = row.config or {}
        raw_store = (cfg.get("store_url") or cfg.get("storeUrl") or "").strip()
        access_token = (cfg.get("access_token") or cfg.get("accessToken") or "").strip()
        api_version = (cfg.get("api_version") or "2024-10").strip()

        if not raw_store or not access_token:
            raise RuntimeError("Shopify store_url and access_token are required")

        store_host = raw_store.replace("https://", "").replace("http://", "").strip("/")
        endpoint = f"https://{store_host}/admin/api/{api_version}/orders.json"
        if not is_safe_outbound_url(endpoint, require_https=True):
            raise RuntimeError("Shopify endpoint is not allowed")

        params: Dict[str, Any] = {
            "status": "any",
            "limit": 1,
            "name": order_name,
        }
        if email:
            params["email"] = email

        try:
            resp = requests.get(
                endpoint,
                headers={
                    "X-Shopify-Access-Token": access_token,
                    "Content-Type": "application/json",
                },
                params=params,
                timeout=8,
            )
        except Exception as exc:
            raise RuntimeError(f"Shopify request failed: {str(exc)}")

        if resp.status_code in (401, 403):
            raise RuntimeError("Shopify credentials rejected")
        if resp.status_code >= 400:
            raise RuntimeError(f"Shopify API error ({resp.status_code})")

        body = resp.json() if resp.content else {}
        orders = body.get("orders", []) if isinstance(body, dict) else []
        if not orders:
            return {
                "found": False,
                "order": None,
            }

        order = orders[0]
        return {
            "found": True,
            "order": {
                "id": order.get("id"),
                "name": order.get("name"),
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
                "cancelled_at": order.get("cancelled_at"),
                "created_at": order.get("created_at"),
                "total_price": order.get("total_price"),
                "currency": order.get("currency"),
                "customer_email": (order.get("customer") or {}).get("email") or order.get("email"),
            },
        }

    async def lookup_shopify_order_async(
        self,
        db: Session,
        tenant_id: str,
        bot_id: int,
        order_name: str,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        bot = self._get_bot(db, tenant_id, bot_id)
        if not bot:
            raise ValueError("Bot not found")

        row = self._get_integration(db, bot_id, "shopify")
        if not row or not row.is_active:
            raise RuntimeError("Shopify integration is not active")

        cfg = row.config or {}
        raw_store = (cfg.get("store_url") or cfg.get("storeUrl") or "").strip()
        access_token = (cfg.get("access_token") or cfg.get("accessToken") or "").strip()
        api_version = (cfg.get("api_version") or "2024-10").strip()

        if not raw_store or not access_token:
            raise RuntimeError("Shopify store_url and access_token are required")

        store_host = raw_store.replace("https://", "").replace("http://", "").strip("/")
        endpoint = f"https://{store_host}/admin/api/{api_version}/orders.json"
        if not is_safe_outbound_url(endpoint, require_https=True):
            raise RuntimeError("Shopify endpoint is not allowed")

        params: Dict[str, Any] = {"status": "any", "limit": 1, "name": order_name}
        if email:
            params["email"] = email

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    endpoint,
                    headers={
                        "X-Shopify-Access-Token": access_token,
                        "Content-Type": "application/json",
                    },
                    params=params,
                )
        except Exception as exc:
            raise RuntimeError(f"Shopify request failed: {str(exc)}")

        if resp.status_code in (401, 403):
            raise RuntimeError("Shopify credentials rejected")
        if resp.status_code >= 400:
            raise RuntimeError(f"Shopify API error ({resp.status_code})")

        body = resp.json() if resp.content else {}
        orders = body.get("orders", []) if isinstance(body, dict) else []
        if not orders:
            return {"found": False, "order": None}

        order = orders[0]
        return {
            "found": True,
            "order": {
                "id": order.get("id"),
                "name": order.get("name"),
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
                "cancelled_at": order.get("cancelled_at"),
                "created_at": order.get("created_at"),
                "total_price": order.get("total_price"),
                "currency": order.get("currency"),
                "customer_email": (order.get("customer") or {}).get("email") or order.get("email"),
            },
        }


integration_service = IntegrationService()
