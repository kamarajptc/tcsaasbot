import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from sqlalchemy.orm import Session
from app.core.database import EmailSettingsDB

logger = logging.getLogger("TangentCloud")

class EmailService:
    def send_email(self, db: Session, tenant_id: str, subject: str, body: str, recipient: str = None):
        """
        Sends an email using the tenant's SMTP configuration.
        """
        config = db.query(EmailSettingsDB).filter(EmailSettingsDB.tenant_id == tenant_id).first()
        
        if not config or not config.is_enabled:
            logger.warning("email_disabled_or_unconfigured", extra={"tenant_id": tenant_id})
            return False

        # If no recipient provided, send to the configured sender (admin)
        to_email = recipient or config.sender_email
        
        try:
            msg = MIMEMultipart()
            msg['From'] = config.sender_email
            msg['To'] = to_email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'html'))
            
            # Best effort + timeout keeps failures retry-safe for upstream lead writes.
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(config.smtp_user, config.smtp_pass)
                server.send_message(msg)
            
            logger.info("email_sent", extra={"tenant_id": tenant_id, "recipient": to_email})
            return True
            
        except Exception as e:
            logger.warning("email_send_failed", extra={
                "tenant_id": tenant_id,
                "recipient": to_email,
                "error": str(e),
                "error_type": type(e).__name__,
            })
            return False

    def notify_new_lead(self, db: Session, tenant_id: str, lead_data: dict):
        """
        Notifies the tenant admin about a new lead.
        """
        subject = "🚀 New Lead Captured!"
        body = f"""
        <h2>Great news!</h2>
        <p>A new lead has been captured from your chatbot.</p>
        <pre>{lead_data}</pre>
        <p>Log in to your dashboard to see more details.</p>
        """
        return self.send_email(db, tenant_id, subject, body)

    def notify_usage_limit(self, db: Session, tenant_id: str, current_usage: int, limit: int):
        """
        Alerts the tenant when they reach 90% of their plan limit.
        """
        subject = "⚠️ Usage Alert: Approaching Limit"
        body = f"""
        <h2>Usage Alert</h2>
        <p>You have reached {current_usage} out of {limit} messages in your current plan.</p>
        <p>Please upgrade your plan to avoid service interruption.</p>
        """
        return self.send_email(db, tenant_id, subject, body)

email_service = EmailService()
