import asyncio
import logging
import os, sys

import dotenv
dotenv.load_dotenv()

from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram import types

from models import TelegramUser, Note
from tortoise import Tortoise
from generate_schema import init

# Bot token can be obtained via https://t.me/BotFather
TOKEN = os.getenv('TG_BOT_TOKEN')

# All handlers should be attached to the Router (or Dispatcher)

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    """
    This handler receives messages with the `/start` command
    """
    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    welcome_message = (
        f"👋 Привет, {user.first_name}!\n\n"
        "✨ <b>Добро пожаловать в Saved AI!</b> ✨\n\n"
        "Представь себе личного помощника, который запоминает все присланные сообщения, ищет необходимую информацию "
        "и позволяет тебе общаться с твоей собственной базой знаний в любое время.\n\n"
        "📚 <b>Функции:</b>\n"
        "- Сохранение заметок\n"
        "- Гибкий поиск\n"
        "- Взаимодействие с базой знаний для получения ответов на любые вопросы\n\n"
        "🔒 <b>480 р / мес, чтобы получить доступ к боту:\n</b> /subscribe"
    )

    await message.answer(welcome_message, parse_mode=ParseMode.HTML)

@dp.message(Command('help'))
async def cmd_help(message: types.Message):
    help_text = (
        "Вот, что я могу:\n\n"
        "/search 🔎 - Your notes\n"
        "/chat 💬 - With the knowledge base\n"
        "/note ✍️ - Back to notes mode\n"
        "/link 🔗 - Invite friends with discount\n"
        "/subscribe ✅ - Your access to the bot\n"
        "/update 🔄 - Update the vector store\n"
        "/help ℹ️ - What can I do?"
    )

    await message.answer(help_text)



async def main() -> None:

    # Initialize Tortoise ORM
    await init()

    # Initialize Bot instance with default bot properties which will be passed to all API calls
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # And the run events dispatching
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())