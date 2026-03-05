import os
import sys

# Add the current directory to sys.path to import app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.database import get_db
from app.models.bot import Bot

def update_welcome_messages():
    db = next(get_db())
    try:
        # Update all bots that have the old default welcome message
        old_messages = [
            "Hi! How can I help you today?",
            "Hello. How can I help you today?",
        ]

        bots_updated = 0
        for old_msg in old_messages:
            bots = db.query(Bot).filter(Bot.welcome_message == old_msg).all()
            for bot in bots:
                bot.welcome_message = "Welcome to TangentCloud. Ask me anything."
                bots_updated += 1

        db.commit()
        print(f"Updated welcome messages for {bots_updated} bots")

    except Exception as e:
        print(f"Error updating welcome messages: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_welcome_messages()