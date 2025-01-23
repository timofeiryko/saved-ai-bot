import aiogram
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import aiogram.exceptions
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram import types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.deep_linking import create_start_link

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from apscheduler_di import ContextSchedulerDecorator
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from models import TelegramUser, Note, UserMessage
from tortoise import Tortoise
from generate_schema import init
from backend import upload_notes_to_pinecone, search_notes, start_kb_chat, continue_kb_chat, upload_exported_chat_to_pinecone
from parse_telegram_json_polars import parse_telegram_chat
from text_tools import generate_wordcloud

import asyncio
import logging
import os
import sys
import datetime

import dotenv
dotenv.load_dotenv(override=True)

# Bot token can be obtained via https://t.me/BotFather
TOKEN = os.getenv('TG_BOT_TOKEN')
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()

UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', 60))
PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN')

JOBSTORES = {
    'default': RedisJobStore(jobs_key='jobs', run_times_key='run_times', host='localhost', port=6379)
}

scheduler = ContextSchedulerDecorator(AsyncIOScheduler(jobstores=JOBSTORES))
scheduler.ctx.add_instance(bot, Bot)

redis_storage = RedisStorage.from_url('redis://localhost:6379')
dp = Dispatcher(storage=redis_storage)

class States(StatesGroup):
    notes = State()
    chat = State()
    search = State()
    subscription_choice = State()
    wait_for_payment = State()
    wait_for_json = State()

PRICE_1_MONTH = 640
PRICE_3_MONTHS = 580
PRICE_6_MONTHS = 540
PRICE_12_MONTHS = 480
INVITE_DISCOUNT = 0.8

FREE_USERS = ['ryko_official', 'netnet_dada', 'AristotelPetrov', 'donRumata03', 'Minlos', 'youryouthhh', 'random_chemist_name_7', 'MLfroge']

async def check_subscription(user: TelegramUser):

    has_active_subscription = await user.has_active_subscription()

    if user.username in FREE_USERS:
        return True

    return has_active_subscription

def get_subscription_keyboard(discount: float = 1.0) -> types.ReplyKeyboardMarkup:

    builder = ReplyKeyboardBuilder()

    keyboard = []
    keyboard.append(types.KeyboardButton(text=f'1 месяц ({PRICE_1_MONTH * discount:.0f} ₽ / мес)'))
    builder.row(*keyboard)

    keyboard = []
    keyboard.append(types.KeyboardButton(text=f'3 месяца ({PRICE_3_MONTHS * discount:.0f} ₽ / мес) | На 1️⃣0️⃣ % выгоднее'))
    builder.row(*keyboard)

    keyboard = []
    keyboard.append(types.KeyboardButton(text=f'🔥 Пол года ({PRICE_6_MONTHS * discount:.0f} ₽ / мес) | На 1️⃣5️⃣ % выгоднее'))
    builder.row(*keyboard)

    keyboard = []
    keyboard.append(types.KeyboardButton(text=f'🔥🔥🔥 Год ({PRICE_12_MONTHS * discount:.0f} ₽ / мес) | На 2️⃣5️⃣ % выгоднее'))
    builder.row(*keyboard)

    return builder.as_markup(resize_keyboard=True)

@dp.message(CommandStart(deep_link=False))
async def command_start_handler_raw(message: types.Message, state: FSMContext, command: CommandObject):
    await command_start_handler(message, state, command)

@dp.message(CommandStart(deep_link=True))
async def command_start_handler(message: types.Message, state: FSMContext, command: CommandObject):
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

    price = PRICE_12_MONTHS
    invited_message = None

    invited_by = command.args
    if invited_by:

        invited_by_user = await TelegramUser.get(telegram_id=invited_by)
        if invited_by_user:
            user.invited_by = invited_by_user
            await user.save()

        invited_message = f'🎁 Специально для тебя действует скидка 20% на подписку, так как тебя пригласил @{invited_by_user.username}'        
        price = PRICE_12_MONTHS * INVITE_DISCOUNT

        # Add flag that there is a discount 
        await state.update_data(invited_disount=True)

    welcome_message = (
        f"👋 Привет, {user.first_name}!\n\n"
        "✨ <b>Добро пожаловать в Saved AI!</b> ✨\n\n"
        "Представь себе личного помощника, который запоминает все присланные сообщения, ищет необходимую информацию "
        "и позволяет тебе общаться с твоей собственной базой знаний в любое время.\n\n"
        "📚 <b>Функции:</b>\n"
        "- Импорт любых чатов и каналов в Telegram\n"
        "- Сохранение заметок\n"
        "- Гибкий поиск\n"
        "- Взаимодействие с базой знаний для получения ответов на любые вопросы\n\n"
        f"🔒 <b>{price:.0f} р / мес, чтобы получить доступ к боту:\n</b> /subscribe"
    )

    if invited_message:
        welcome_message += f'\n\n{invited_message}'

    await state.set_state(States.notes)
    await message.answer(welcome_message, parse_mode=ParseMode.HTML)

@dp.message(Command('help'))
async def cmd_help(message: types.Message):
    help_text = (
        "Вот, что я могу:\n\n"
        "/search 🔎 - Your notes\n"
        "/chat 💬 - With the knowledge base\n"
        "/note ✍️ - Back to notes mode\n"
        "/import 📥 - Import notes from Telegram\n"
        "/link 🔗 - Invite friends with discount\n"
        "/subscribe ✅ - Your access to the bot\n"
        "/update 🔄 - Update the vector store\n"
        "/help ℹ️ - What can I do?"
    )

    await message.answer(help_text)

@dp.message(Command('link'))
async def cmd_link(message: types.Message):

    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )
    invited_count = await user.invited_users_count
    link = await create_start_link(bot, user.telegram_id)
    message_text = f'Все, кто зарегистрируются по этой ссылке, получат скидку 20% на бот Saved AI, а ты - 20% на следующую подписку:\n\n{link}\n\nСейчас приглашено: {invited_count} 👤'

    await message.answer(message_text)

@dp.message(Command('import'))
async def cmd_import(message: types.Message, state: FSMContext):

    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    has_active_subscription = await check_subscription(user)
    if not has_active_subscription:
        await message.answer('Для импорта заметок нужно оформить подписку: /subscribe')
        return
    
    image_path = 'image.png'
    image_from_pc = types.FSInputFile(image_path)

    await state.set_state(States.wait_for_json)

    await message.answer_photo(
        photo=image_from_pc,
        caption='Отправь мне чат или канал, который хочешь импортировать в формате JSON. Не включай изображения в файл! Вот как это сделать ⬇️',
        show_caption_above_media=True,
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(Command('subscribe'))
async def cmd_subscribe(message: types.Message, state: FSMContext):
    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    await state.set_state(States.subscription_choice)

    data = await state.get_data()
    invited_disount = data.get('invited_disount', False)
    if invited_disount:
        discount = INVITE_DISCOUNT
    else:
        discount = 1.0

    await message.answer(
        'Выбери срок подписки. Чем дольше, тем дешевле 😉',
        reply_markup=get_subscription_keyboard(discount=discount)
    )

@dp.message(Command('note'))
async def cmd_note_mode(message: types.Message, state: FSMContext):
    await state.set_state(States.notes)
    await message.answer('Добавляй заметки, а я их запомню ✍️')

@dp.message(Command('chat'))
async def cmd_chat_mode(message: types.Message, state: FSMContext):

    await state.clear()

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

    has_active_subscription = await check_subscription(user)
    if not has_active_subscription:
        await message.answer('Для обновления базы знаний нужно оформить подписку: /subscribe')
        return

    await upload_notes_to_pinecone(user)
    await message.answer('Обновил базу знаний 🔄')

@dp.message(States.subscription_choice)
async def process_subscription_choice(message: types.Message, state: FSMContext):

    data = await state.get_data()
    invited_disount = data.get('invited_disount', False)
    if invited_disount:
        discount = INVITE_DISCOUNT
    else:
        discount = 1.0

    valid_choices = get_subscription_keyboard(discount=discount).keyboard
    valid_choices = [button[0].text for button in valid_choices]

    if message.text not in valid_choices:
        await message.answer('Выбери один из вариантов на клавиатуре ⬇️', reply_markup=get_subscription_keyboard(discount=discount))
        return
    
    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    price = None
    if message.text == valid_choices[0]:
        title = 'Подписка на 1 месяц'
        months_num = 1
        price = PRICE_1_MONTH * months_num
    elif message.text == valid_choices[1]:
        title = 'Подписка на 3 месяца'
        months_num = 3
        price = PRICE_3_MONTHS * months_num
    elif message.text == valid_choices[2]:
        title = 'Подписка на 6 месяцев'
        months_num = 6
        price = PRICE_6_MONTHS * months_num
    elif message.text == valid_choices[3]:
        title = 'Подписка на 12 месяцев'
        months_num = 12
        price = PRICE_12_MONTHS * months_num
    else:
        await message.answer('Что-то пошло не так, попробуй еще раз: /subscribe')
        return

    # If invited by someone, apply discount
    data = await state.get_data()
    invited_disount = data.get('invited_disount', False)
    if invited_disount:
        price = price * INVITE_DISCOUNT
    
    await state.set_state(States.wait_for_payment)


    await message.answer_invoice(
        title=title,
        description='Доступ к боту Saved AI',
        payload=f'subscribe_{months_num}',
        currency='RUB',
        prices=[types.LabeledPrice(label='Подписка', amount=price*100)],
        provider_token=PROVIDER_TOKEN
    )

@dp.pre_checkout_query()
async def process_precheckout_query(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):

    goal, months_num = message.successful_payment.invoice_payload.split('_')
    months_num = int(months_num)

    # get state from storage
    key = StorageKey(bot.id, message.from_user.id, message.from_user.id)
    state = FSMContext(dp.storage, key)

    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    if goal == 'subscribe':

        await user.activate_subscription(days=30*months_num)
        await message.answer(f'Подписка на {months_num} месяцев активирована ✅\nИстекает {user.subscription_end_date.date()}', reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(States.notes)

        flag = await user.has_active_subscription()
        if not flag:
            print('SUBSCRIPTION NOT ACTIVE, SOMETHING WRONG')
    
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

    has_active_subscription = await check_subscription(user)
    if not has_active_subscription:
        await message.answer('Для общения с базой знаний нужно оформить подписку: /subscribe')
        return

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

        await message.answer(results.get('answer', ''), parse_mode=ParseMode.MARKDOWN, reply_markup=types.ReplyKeyboardRemove())
        await message.answer('Мой ответ основан на следующих сообщениях:', reply_markup=types.ReplyKeyboardRemove())

        sent_messages_ids = set()
        for result in results.get('context', []):
            try:
                message_id = result.metadata['source']
            except KeyError:
                continue
            if message_id in sent_messages_ids:
                continue
            sent_messages_ids.add(message_id)
            await message.bot.forward_message(
                message.chat.id,
                from_chat_id=message.chat.id,
                message_id=message_id
            )

        sent_messages = set()
        for result in results.get('context', []):
            try:
                date = result.metadata['date']
            except KeyError:
                continue
            message_from_imported_chat = result.page_content
            message_from_imported_chat += f'\n\nDate: {date.split('T')[0]}'
            if message_from_imported_chat in sent_messages:
                continue
            sent_messages.add(message_from_imported_chat)

            messages_parts = message_from_imported_chat.split('From the chat: ')
            part_monospace = f'```\n{messages_parts[0]}```'
            part_info = f'From the chat: {messages_parts[1]}'
            message_from_imported_chat = part_monospace + part_info

            await message.answer(message_from_imported_chat, parse_mode=ParseMode.MARKDOWN)


        await message.answer('Теперь я могу обсудить найденные заметки, но чтобы найти другие, отправь /chat')

@dp.message(States.wait_for_json)
async def process_json_file(message: types.Message, state: FSMContext):

    user, _ = await TelegramUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username or "there",
            'first_name': message.from_user.first_name or "",
            'last_name': message.from_user.last_name or ""
        }
    )

    has_active_subscription = await check_subscription(user)
    if not has_active_subscription:
        await message.answer('Для импорта заметок нужно оформить подписку: /subscribe')
        return

    file_id = message.document.file_id
    try:
        file = await bot.get_file(file_id)
    except aiogram.exceptions.TelegramBadRequest:
        await message.answer('Кажется, файл больше 20 Мб ☹️. При экспорте установи диапозон дат и попробуй снова')


    if not file.file_path.endswith('.json'):
        await message.answer('Пожалуйста, отправь файл в формате JSON')
        return

    await message.reply('💬')

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    file_name = os.path.join('exported_chats', f'chat_{file_id}stamp_{timestamp}.json')
    await bot.download_file(file.file_path, file_name)
    

    df, chat_name = parse_telegram_chat(file_name)
    wordcloud_path = generate_wordcloud(df, chat_name)
    wordcloud_image = types.FSInputFile(wordcloud_path)

    await upload_exported_chat_to_pinecone(user, df, chat_name)

    await message.answer_photo(
        photo=wordcloud_image,
        caption=f'Чат "{chat_name}" успешно импортирован. Лови облако ключевых слов из чата ☁️',
        show_caption_above_media=True,
        reply_markup=types.ReplyKeyboardRemove()
    )

    os.remove(wordcloud_path)

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

    has_active_subscription = await check_subscription(user)
    if not has_active_subscription:
        await message.answer('Для добавления заметок нужно оформить подписку: /subscribe')
        return
    
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

    has_active_subscription = await check_subscription(user)
    if not has_active_subscription:
        await message.answer('Для поиска по заметкам нужно оформить подписку: /subscribe')
        return

    if not await user.limmits_not_exceeded:
        await message.answer("You have exceeded the limit of 30 messages per day or 200 Mb vector storage volume.")
        await state.clear()
        return
    
    search_results = await search_notes(user, message.text)

    sent_messages = set()

    for result in search_results:

        try:
            message_id = result.metadata['source']
        except KeyError:
            continue

        await message.bot.forward_message(
            message.chat.id,
            from_chat_id=message.chat.id,
            message_id=message_id
        )

    for result in search_results:
        try:
            date = result.metadata['date']
        except KeyError:
            continue
        message_from_imported_chat = result.page_content
        message_from_imported_chat += f'\n\nDate: {date.split('T')[0]}'
        if message_from_imported_chat in sent_messages:
            continue
        sent_messages.add(message_from_imported_chat)

        messages_parts = message_from_imported_chat.split('From the chat: ')
        part_monospace = f'```\n{messages_parts[0]}```'
        part_info = f'From the chat: {messages_parts[1]}'
        message_from_imported_chat = part_monospace + part_info

        await message.answer(message_from_imported_chat, parse_mode=ParseMode.MARKDOWN)

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