# test_search.py

import os
import sys
import asyncio
import logging

# Add the parent directory to the sys.path to allow importing from backend and models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tortoise import Tortoise
from tortoise.exceptions import ConfigurationError
from models import TelegramUser
from backend import search_notes  # Ensure that search_notes is correctly imported

import dotenv
dotenv.load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

async def test_search_notes(user: TelegramUser, query: str):
    """Test the search_notes function for a given user and query."""
    logger.info(f"\nTesting search_notes function with query: '{query}'")
    try:
        search_results = await search_notes(user, query)
        print(f"Search Results for query '{query}':")
        print(search_results)
        logger.info("search_notes function executed successfully.")
    
    except Exception as e:
        logger.error(f"Error during search_notes execution: {e}")

async def run_search_test():
    """Run the search_notes test."""
    try:
        # Initialize Database
        await init_db()

        # Define the telegram_id of the user to search for
        telegram_id = TEST_USER_ID  # Replace with the actual telegram_id if different

        # Fetch the user
        user = await fetch_user(telegram_id)

        # Define the search query
        test_search_query = "Написание кода"

        # Perform the search
        await test_search_notes(user, test_search_query)

    except ConfigurationError as ce:
        logger.error(f"Configuration Error: {ce}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        # Close Database Connections
        await Tortoise.close_connections()
        logger.info("Tortoise ORM connections closed.")

if __name__ == '__main__':
    asyncio.run(run_search_test())
