import stripe
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import TenantDB, StripeEventDB
import logging

settings = get_settings()
stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")

logger = logging.getLogger("TangentCloud")

class BillingService:
    def _is_mock_or_empty(self, value: str, mock_prefixes):
        raw = (value or "").strip()
        return (not raw) or any(raw.startswith(prefix) for prefix in mock_prefixes)

    def _validate_checkout_config(self, plan: str):
        if self._is_mock_or_empty(settings.STRIPE_SECRET_KEY, ("sk_test_mock",)):
            raise ValueError("Stripe is not configured. Missing STRIPE_SECRET_KEY.")
        if plan == "pro" and self._is_mock_or_empty(settings.STRIPE_PRICE_PRO_ID, ("price_mock",)):
            raise ValueError("Stripe pro plan is not configured. Missing STRIPE_PRICE_PRO_ID.")
        if plan == "enterprise" and self._is_mock_or_empty(settings.STRIPE_PRICE_ENT_ID, ("price_mock",)):
            raise ValueError("Stripe enterprise plan is not configured. Missing STRIPE_PRICE_ENT_ID.")

    def create_checkout_session(self, db: Session, tenant_id: str, plan: str):
        """
        Creates a Stripe Checkout Session for a tenant to upgrade their plan.
        """
        self._validate_checkout_config(plan)
        stripe.api_key = settings.STRIPE_SECRET_KEY

        tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
        if not tenant:
            raise ValueError("Tenant not found")

        # Map plan internal names to Stripe Price IDs (Usually from env)
        prices = {
            "pro": settings.STRIPE_PRICE_PRO_ID,
            "enterprise": settings.STRIPE_PRICE_ENT_ID
        }

        price_id = prices.get(plan)
        if not price_id:
            raise ValueError(f"Invalid plan: {plan}")

        try:
            # Create/Retrieve Stripe Customer
            if not tenant.stripe_customer_id:
                customer = stripe.Customer.create(
                    email=f"{tenant_id}@customer.com", # In real app, use tenant email
                    metadata={"tenant_id": tenant_id}
                )
                tenant.stripe_customer_id = customer.id
                db.commit()

            session = stripe.checkout.Session.create(
                customer=tenant.stripe_customer_id,
                payment_method_types=['card'],
                line_items=[{'price': price_id, 'quantity': 1}],
                mode='subscription',
                success_url=f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/settings?success=true",
                cancel_url=f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/settings?canceled=true",
                metadata={"tenant_id": tenant_id, "plan": plan}
            )
            return session.url
        except Exception as e:
            logger.error(f"Stripe Session Error: {str(e)}")
            raise e

    def handle_webhook(self, db: Session, payload: bytes, sig_header: str):
        """
        Handles Stripe Webhook events to sync subscription status.
        """
        if self._is_mock_or_empty(settings.STRIPE_SECRET_KEY, ("sk_test_mock",)):
            logger.error("webhook_rejected_missing_secret_key")
            return False
        if self._is_mock_or_empty(settings.STRIPE_WEBHOOK_SECRET, ("whsec_mock",)):
            logger.error("webhook_rejected_missing_webhook_secret")
            return False

        stripe.api_key = settings.STRIPE_SECRET_KEY

        event = None
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            logger.error(f"Webhook Signature Error: {str(e)}")
            return False

        event_id = event.get("id")
        if not event_id:
            logger.error("webhook_missing_event_id")
            return False

        existing = db.query(StripeEventDB).filter(StripeEventDB.event_id == event_id).first()
        if existing:
            logger.info(f"Stripe event {event_id} already processed; skipping duplicate.")
            return True

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            tenant_id = session['metadata'].get('tenant_id')
            plan = session['metadata'].get('plan')
            
            if tenant_id and plan:
                tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
                if tenant:
                    tenant.plan = plan
                    tenant.stripe_subscription_id = session.get('subscription')
                    logger.info(f"Tenant {tenant_id} successfully upgraded to {plan}")

        db_event = StripeEventDB(
            event_id=event_id,
            event_type=event.get("type", "unknown"),
            tenant_id=event.get("data", {}).get("object", {}).get("metadata", {}).get("tenant_id"),
        )
        db.add(db_event)
        db.commit()
        return True

billing_service = BillingService()
