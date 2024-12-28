import os
import asyncio
import logging

import sys
# Add the parent directory to the sys.path to allow importing from backend and models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tortoise import Tortoise
from tortoise.exceptions import ConfigurationError
from models import TelegramUser, Note
from backend import upload_notes_to_pinecone

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

async def create_example_user():
    """Create an example TelegramUser."""
    user = await TelegramUser.create(
        telegram_id=TEST_USER_ID,  # Example Telegram user ID
        username='testuser',
        first_name='Test',
        last_name='User'
    )
    logger.info(f"Created User: {user}")
    return user

async def create_notes_for_user(user, num_notes=10):
    """Create a specified number of Note instances for the user with larger Russian content."""
    russian_texts = [
        "Сегодня отличный день для изучения новой информации. Я планирую пройти несколько онлайн-курсов по программированию и улучшить свои навыки в области искусственного интеллекта. Это позволит мне создавать более сложные и эффективные приложения в будущем.",
        "Программирование - это увлекательный процесс, который позволяет создавать новые приложения и решать сложные задачи. Каждый день приносит новые вызовы и возможности для роста, что делает эту область невероятно динамичной и интересной.",
        "Заметки помогают организовать мысли и идеи, а также облегчают возвращение к ним в будущем. Я стараюсь записывать все важные моменты, чтобы ничего не упустить и иметь возможность анализировать свои идеи более глубоко.",
        "Искусственный интеллект быстро развивается и находит применение во множестве сфер, от медицины до транспорта. Это революционная технология, которая изменит наше будущее, сделав его более эффективным и безопасным.",
        "Чтение книг расширяет кругозор и обогащает словарный запас. Сегодня я прочитал несколько глав из новой научно-фантастической книги и был поражен её глубиной и продуманностью сюжета, что вдохновило меня на создание своих собственных историй.",
        "Спорт улучшает физическое и психическое здоровье. Регулярные тренировки помогают поддерживать форму, повышают выносливость и укрепляют иммунную систему, а также способствуют снижению уровня стресса.",
        "Музыка способна поднять настроение и снять стресс. В свободное время я люблю слушать классическую музыку и играть на гитаре, что помогает мне расслабиться и найти вдохновение для новых проектов.",
        "Путешествия обогащают жизненный опыт и позволяют узнать новые культуры. Я мечтаю посетить несколько стран и познакомиться с их традициями и обычаями, чтобы лучше понимать мир вокруг нас.",
        "Кулинария - это творческий процесс, который позволяет экспериментировать с различными ингредиентами и рецептами. Готовка доставляет удовольствие и радует окружающих, будучи отличным способом выразить свою креативность.",
        "Наука играет ключевую роль в прогрессе общества. Благодаря исследованиям и открытиям мы можем решать сложные проблемы и улучшать качество жизни людей, внедряя инновационные решения во всех сферах жизни."
    ]
    
    for i in range(num_notes):
        note = await Note.create(
            text=russian_texts[i],
            user=user,
            telegram_message_id=2000 + i  # Example Telegram message IDs
        )
        logger.info(f"Created Note: {note}")

async def run_tests():
    """Run the testing process."""

    try:

        # Initialize Database
        await init_db()

        # Create Example User
        user = await create_example_user()

        # Create 10 Notes for the User with larger Russian content
        await create_notes_for_user(user, num_notes=10)

        # Test upload_notes_to_pinecone
        logger.info("\nTesting upload_notes_to_pinecone function...")
        await upload_notes_to_pinecone(user)
        logger.info("upload_notes_to_pinecone function executed successfully.")
        
        
    except ConfigurationError as ce:
        logger.error(f"Configuration Error: {ce}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        # Close Database Connections
        await Tortoise.close_connections()
        logger.info("Tortoise ORM connections closed.")

if __name__ == '__main__':
    asyncio.run(run_tests())
