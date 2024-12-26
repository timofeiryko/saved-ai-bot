import os, sys, aiofiles
import datetime
import logging

import openai
import backoff
import asyncio

from models import TelegramUser, Note
from tortoise import Tortoise

import dotenv
dotenv.load_dotenv()

OPENAI_KEY = os.getenv('OPENAI_KEY')
client = openai.AsyncClient(api_key=OPENAI_KEY)
ASSISTANT_PROMPT = 'You are a helpful assistant that helps users with their notes. User can search his knowledge base, chat with the assistant, and add new notes. The user can ask questions, get answers, and receive recommendations. The assistant should be able to understand the context of the conversation and provide relevant responses.'

async def _wait_for_run_completion(client, thread_id: str, run_id: str, sleep_interval: int = 1):
    while True:
        run = await client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        if run.completed_at:
            break
        await asyncio.sleep(sleep_interval)

async def generate_txt_from_notes(user_id: int) -> str:

    user = await TelegramUser.get(telegram_id=user_id)
    notes = await user.notes.all()
    notes_text = "\n\n".join([note.text for note in notes])

    # Write notes to a file with timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{user_id}_{timestamp}.txt"
    async with aiofiles.open(filename, 'w') as f:
        await f.write(notes_text)

    return filename

async def create_store_for_user(user_id):
    
    store_name = f"store_{user_id}"
    vector_store = await client.beta.vector_stores.create(name=store_name)

    notes_filename = await generate_txt_from_notes(user_id)
    file_streams = [open(notes_filename, 'rb')]

    file_batch = await client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store.id,
        files=file_streams
    )

    assistant = await client.beta.assistants.create(
        name=f'knowledge_base_assistant_{user_id}',
        instructions=ASSISTANT_PROMPT,
        model='gpt-4o-mini',
        tools=[{'type': 'file_search'}]
    )

    assistant = await client.beta.assistants.update(
        assistant_id=assistant.id,
        tool_resources={'file_search': {'vector_store_ids': [vector_store.id]}}
    )

