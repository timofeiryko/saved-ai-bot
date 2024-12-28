from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram import types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.redis import RedisStorage

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from apscheduler_di import ContextSchedulerDecorator

from models import TelegramUser, Note, UserMessage
from tortoise import Tortoise
from generate_schema import init
from backend import upload_notes_to_pinecone, search_notes, start_kb_chat, continue_kb_chat

import asyncio
import logging
import os
import sys
import datetime

import dotenv
dotenv.load_dotenv()

# Bot token can be obtained via https://t.me/BotFather
TOKEN = os.getenv('TG_BOT_TOKEN')
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()

UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', 60))

JOBSTORES = {
    'default': RedisJobStore(jobs_key='jobs', run_times_key='run_times', host='localhost', port=6380)
}

scheduler = ContextSchedulerDecorator(AsyncIOScheduler(jobstores=JOBSTORES))
scheduler.ctx.add_instance(bot, Bot)


redis_storage = RedisStorage.from_url('redis://localhost:6380')
dp = Dispatcher(storage=redis_storage)

class States(StatesGroup):
    notes = State()
    chat = State()
    search = State()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message, state: FSMContext):
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

    await state.set_state(States.notes)
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

@dp.message(Command('subscribe'))
async def cmd_subscribe(message: types.Message):
    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    await message.answer('''
Подписка на бота пока не доступна. Следи за обновлениями 🚀 Описание услуги:

- Стоимость: 480 рублей в месяц
- Возможности: неограниченное количество запросов к базе знаний и сохранение заметок
''')

@dp.message(Command('note'))
async def cmd_note_mode(message: types.Message, state: FSMContext):
    await state.set_state(States.notes)
    await message.answer('Добавляй заметки, а я их запомню ✍️')

@dp.message(Command('chat'))
async def cmd_chat_mode(message: types.Message, state: FSMContext):
    await state.set_state(States.chat)
    await message.answer('Чат с базой знаний активирован. Задавай вопросы 💬')

@dp.message(Command('search'))
async def cmd_search(message: types.Message, state: FSMContext):
    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    if not await user.limmits_not_exceeded:
        await message.answer("You have exceeded the limit of 30 messages per day or 200 vector storage volume.")
        return
    
    notes = await user.notes.all()
    if not notes:
        await message.answer('У тебя пока нет заметок')
        return
    
    await state.set_state(States.search)
    await message.answer('Введи свой поисковый запрос 🔎')

@dp.message(Command('update'))
async def cmd_update_pincone(message: types.Message):
    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    await upload_notes_to_pinecone(user)
    await message.answer('Обновил базу знаний 🔄')

@dp.message(States.chat)
async def chat_with_kb(message: types.Message, state: FSMContext):

    if not message.text:
        await message.answer('Пожалуйста, отправь текстовое сообщение')

    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    if not await user.limmits_not_exceeded:
        await message.answer("You have exceeded the limit of 30 messages per day or 200 vector storage volume.")
        await state.clear()
        return
    
    data = await state.get_data()
    thread_id = data.get('thread_id')
    assistant_id = data.get('assistant_id')

    if thread_id and assistant_id:

        output, thread_id, assistant_id = await continue_kb_chat(user, message.text, data['thread_id'], data['assistant_id'])
        await state.update_data(thread_id=thread_id, assistant_id=assistant_id)
        await message.answer(output, parse_mode=ParseMode.MARKDOWN)

        return
    
    else:

        results, thread_id, assistant_id = await start_kb_chat(user, message.text)
        await state.update_data(thread_id=thread_id, assistant_id=assistant_id)

        await message.answer(results.get('answer', ''), parse_mode=ParseMode.MARKDOWN)

        sent_messages_ids = set()
        for result in results.get('context', []):
            message_id = result.metadata['source']
            if message_id in sent_messages_ids:
                continue
            sent_messages_ids.add(message_id)
            await message.bot.forward_message(
                message.chat.id,
                from_chat_id=message.chat.id,
                message_id=message_id
            )

        await message.answer('Теперь я могу обсудить найденные заметки, но чтобы найти другие, отправь /chat')



@dp.message(States.notes)
async def add_note(message: types.Message):

    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    
    # If there are no notes yet (so this one is the first), update the vector store
    FIRST_FLAG = False
    if not await user.notes.all():
        FIRST_FLAG = True

    if not await user.limmits_not_exceeded:
        await message.answer("You have exceeded the limit of 30 messages per day or 200 vector storage volume.")
        return

    note_text = None
    if message.content_type == 'text':
        note_text = message.text
    elif message.caption:
        note_text = message.caption

    if not note_text:
        await message.answer('Не могу сохранить пустую заметку')
        return

    note = await Note.create(
        text=note_text,
        user=user,
        telegram_message_id=message.message_id
    )
    await note.save()

    if FIRST_FLAG:
        await upload_notes_to_pinecone(user)

    await message.reply('Запомнил 👌')

@dp.message(States.search)
async def process_search_query(message: types.Message, state: FSMContext):
    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    if not await user.limmits_not_exceeded:
        await message.answer("You have exceeded the limit of 30 messages per day or 200 vector storage volume.")
        await state.clear()
        return
    
    search_results = await search_notes(user, message.text)

    for result in search_results:
        message_id = result.metadata['source']

        await message.bot.forward_message(
            message.chat.id,
            from_chat_id=message.chat.id,
            message_id=message_id
        )

    if not search_results:
        await message.answer('Ничего не найдено😕 Попробуй другой запрос')
        return

    await state.clear()

async def scheduled_pinecone_update():

    users = await TelegramUser.all()
    for user in users:
        await upload_notes_to_pinecone(user)
        await asyncio.sleep(1)

    logging.info('Updated Pinecone')

async def main() -> None:

    # Initialize Tortoise ORM
    await init()

    # Initialize Bot instance with default bot properties which will be passed to all API calls
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    scheduler.start()
    scheduler.add_job(scheduled_pinecone_update, 'interval', minutes=UPDATE_INTERVAL, id='pinecone_update', replace_existing=True)

    # And the run events dispatching
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())