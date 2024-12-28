# test_start_kb_chat.py

import os
import sys
import asyncio
import logging

# Add the parent directory to the sys.path to allow importing from backend and models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tortoise import Tortoise
from tortoise.exceptions import ConfigurationError
from models import TelegramUser
from backend import start_kb_chat

import dotenv   
dotenv.load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure that TEST_USER_ID is set in your .env file
TEST_USER_ID = os.getenv('TEST_USER_ID')

async def init_db():
    """Initialize Tortoise ORM."""
    await Tortoise.init(
        db_url='sqlite://db.sqlite3',  # Ensure this matches your actual database URL
        modules={'models': ['models']}  # Correct module reference pointing to models.py
    )
    await Tortoise.generate_schemas()
    logger.info("Tortoise ORM initialized and schemas generated.")

async def fetch_user(telegram_id: int) -> TelegramUser:
    """Fetch the TelegramUser by telegram_id."""
    try:
        user = await TelegramUser.get(telegram_id=telegram_id)
        logger.info(f"Fetched User: {user}")
        return user
    except TelegramUser.DoesNotExist:
        logger.error(f"User with telegram_id {telegram_id} does not exist.")
        raise

async def test_start_kb_chat(user: TelegramUser, message: str):
    """
    Test the start_kb_chat function for a given user and message.

    Args:
        user (TelegramUser): The user for whom to start the chat.
        message (str): The message to send to the assistant.
    """
    logger.info(f"\nTesting start_kb_chat function with message: '{message}'")
    try:
        response = await start_kb_chat(user, message)
        print(f"Response from start_kb_chat for message '{message}':")
        print(response)
        logger.info("start_kb_chat function executed successfully.")
    
    except Exception as e:
        logger.error(f"Error during start_kb_chat execution: {e}")

async def run_chat_test():
    """Run the start_kb_chat test."""
    try:
        # Initialize Database
        await init_db()

        # Define the telegram_id of the user to chat with
        if not TEST_USER_ID:
            raise ValueError("TEST_USER_ID is not set in the environment variables.")
        
        telegram_id = int(TEST_USER_ID)  # Convert to integer if necessary

        # Fetch the user
        user = await fetch_user(telegram_id)

        # Define the chat message related to the existing notes
        test_chat_message = "Расскажи мне о готовке."  # Example in Russian

        # Perform the chat
        await test_start_kb_chat(user, test_chat_message)
    
    except ConfigurationError as ce:
        logger.error(f"Configuration Error: {ce}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        # Close Database Connections
        await Tortoise.close_connections()
        logger.info("Tortoise ORM connections closed.")

if __name__ == '__main__':
    asyncio.run(run_chat_test())
