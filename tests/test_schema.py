import os
import sys

# Add the parent directory to the sys.path to allow importing from backend and models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from tortoise import Tortoise
from tortoise.exceptions import ConfigurationError
from models import TelegramUser, Note, UserMessage
import logging

# Set up logging for better debug information
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_tests():
    try:
        # Initialize Tortoise ORM with the correct module reference
        await Tortoise.init(
            db_url='sqlite://db.sqlite3',  # Ensure this matches your actual database URL
            modules={'models': ['models']}  # Correct module reference pointing to models.py
        )
        await Tortoise.generate_schemas()
        logger.info("Tortoise ORM initialized and schemas generated.")

        # **CREATE**
        logger.info("Creating a new TelegramUser...")
        user = await TelegramUser.create(
            telegram_id=123456789,  # Replace with actual Telegram user ID
            username='johndoe',
            first_name='John',
            last_name='Doe'
        )
        logger.info(f"Created User: {user}")

        logger.info("Creating a new Note for the user...")
        note = await Note.create(
            text='This is a test note.',
            user=user,
            telegram_message_id=987654321  # Replace with actual Telegram message ID
        )
        logger.info(f"Created Note: {note}")

        logger.info("Creating a new UserMessage for the user...")
        message = await UserMessage.create(
            text='This is a test message.',
            user=user,
            telegram_message_id=123123123  # Replace with actual Telegram message ID
        )
        logger.info(f"Created UserMessage: {message}")

        # **READ**
        logger.info("\nFetching the user from the database...")
        fetched_user = await TelegramUser.get(telegram_id=123456789)
        logger.info(f"Fetched User: {fetched_user}")

        logger.info("Fetching notes for the user...")
        notes = await fetched_user.notes.all()
        for n in notes:
            logger.info(f"Note: {n}")

        logger.info("Fetching messages for the user...")
        messages = await fetched_user.user_messages.all()
        for m in messages:
            logger.info(f"UserMessage: {m}")

        # **UPDATE**
        logger.info("\nUpdating the user's username...")
        fetched_user.username = 'john_doe_updated'
        await fetched_user.save()
        logger.info(f"Updated User: {fetched_user}")

        logger.info("Activating subscription for 60 days...")
        await fetched_user.activate_subscription(days=60)
        logger.info(f"Subscription End Date: {fetched_user.subscription_end_date}")

        # **DELETE**
        logger.info("\nDeleting the note...")
        await note.delete()
        remaining_notes = await fetched_user.notes.all()
        logger.info(f"Remaining Notes: {remaining_notes}")

        logger.info("Deleting the UserMessage...")
        await message.delete()
        remaining_messages = await fetched_user.user_messages.all()
        logger.info(f"Remaining UserMessages: {remaining_messages}")

        logger.info("Deleting the user...")
        await fetched_user.delete()
        users = await TelegramUser.all()
        logger.info(f"All Users: {users}")

    except ConfigurationError as ce:
        logger.error(f"Configuration Error: {ce}")
    except Exception as e:
        logger.error(f"An error occurred during tests: {e}")
    finally:
        # Close connections
        await Tortoise.close_connections()
        logger.info("Tortoise ORM connections closed.")

if __name__ == '__main__':
    asyncio.run(run_tests())
