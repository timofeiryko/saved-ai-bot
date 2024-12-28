import os
import sys
import aiofiles
from aiocsv import AsyncWriter
import datetime
import logging
import random
from typing import Optional
from dataclasses import dataclass

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone.vectorstores import Pinecone
from langchain_community.document_loaders import TextLoader, PDFMinerLoader, CSVLoader
from langchain_text_splitters import CharacterTextSplitter

from langchain.agents.openai_assistant import OpenAIAssistantRunnable
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.retrieval import create_retrieval_chain
from langchain.tools import Tool
from langchain.agents import AgentExecutor
from langchain_community.tools import DuckDuckGoSearchRun


from models import TelegramUser
from generate_schema import init
from tortoise import Tortoise

import dotenv
import csv
dotenv.load_dotenv()

@dataclass
class AssistantMessage:
    text: str
    thread_id: str

ASSISTANT_PROMPT = '''
You are a helpful assistant that helps users with their notes. User can search his knowledge base, chat with the assistant, and add new notes.
The assistant should be able to understand the context of the conversation and provide relevant responses.
You are an assistant for question-answering tasks. If you don't know the answer, say that you don't know. Keep the answers concise.

Here is the list of comands in telegram bot:
"/search 🔎 - Your notes\n"
"/chat 💬 - With the knowledge base\n"
"/note ✍️ - Back to notes mode\n"
"/link 🔗 - Invite friends with discount\n"
"/subscribe ✅ - Your access to the bot\n"
"/update 🔄 - Update the vector store\n"
"/help ℹ️ - What can I do?"
Here thie info about the bot:
"✨ <b>Добро пожаловать в Saved AI!</b> ✨\n\n"
"Представь себе личного помощника, который запоминает все присланные сообщения, ищет необходимую информацию "
"и позволяет тебе общаться с твоей собственной базой знаний в любое время.\n\n"
"📚 <b>Функции:</b>\n"
"- Сохранение заметок\n"
"- Гибкий поиск\n"
"- Взаимодействие с базой знаний для получения ответов на любые вопросы\n\n"
"🔒 <b>480 р / мес, чтобы получить доступ к боту:\n</b> /subscribe"

Язык по умолчанию - русский, но пользователь может использовать любой язык для заметок и общения с ассистентом, ассистент должен понимать и отвечать том же языке, который использует пользователь.

Below is the context, including found relevant documents.
'''

ASSISTANT_PROMPT_RAG = '''
You are a helpful assistant that helps users with their notes. User can search his knowledge base, chat with the assistant, and add new notes.
The assistant should be able to understand the context of the conversation and provide relevant responses.
You are an assistant for question-answering tasks. If you don't know the answer, say that you don't know. Keep the answers concise.

Язык по умолчанию - русский, но пользователь может использовать любой язык для заметок и общения с ассистентом, ассистент должен понимать и отвечать том же языке, который использует пользователь.

{context}
'''

RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", ASSISTANT_PROMPT_RAG),
        ("human", "{input}"),
    ]
)

LLM = ChatOpenAI(model="gpt-4o-mini", temperature=0.6)

INDEX_NAMES = (
    'saved-ai-1',
    'saved-ai-2',
    'saved-ai-3'
)

EMBEDDINGS = OpenAIEmbeddings(model='text-embedding-3-small')

async def handle_event(event_text: str):
    """
    Custom function to handle events or deadlines mentioned by the user.
    Extracts the datetime object from the event_text and prints it.
    """
    try:
        # Attempt to parse the datetime from the event_text
        event_datetime = datetime.datetime.fromisoformat(event_text)
        print(f"Event datetime extracted: {event_datetime}")
    except ValueError:
        # If parsing fails, just print the event_text
        print(f"Could not parse datetime from event: {event_text}")

# Define the custom tool
event_tool = Tool(
    name="EventHandler",
    func=handle_event,
    description="Handles any events or deadlines mentioned by the user by extracting and printing the datetime."
)

TOOLS = []

async def fetch_stats(index_name: str, namespace: str):
    # TODO: Implement this function to fetch stats from Pinecone
    pass

async def start_kb_chat(user: TelegramUser, message: str):

    vector_store = Pinecone.from_existing_index(
        index_name=user.index_name,
        namespace=user.vector_storage_namespace,
        embedding=EMBEDDINGS
    )

    retriever = vector_store.as_retriever()

    question_answer_chain = create_stuff_documents_chain(LLM, RAG_PROMPT)
    rag_chain = create_retrieval_chain(retriever, question_answer_chain)

    result = await rag_chain.ainvoke({'input': message})

    agent = await OpenAIAssistantRunnable.acreate_assistant(
        name='notes-ai-pincone',
        instructions=ASSISTANT_PROMPT,
        model='gpt-4o-mini',
        tools=TOOLS,
        as_agent=True
    )

    relevant_docs = result.get('context', [])
    relevant_contents = list(set([doc.page_content for doc in relevant_docs]))
    relevant_contents.append(result.get('answer', ''))
    relevant_contents.append('Carefully analyze relevant documents provided above and just say "OK"')
    context = "\n\n".join([pc for pc in relevant_contents])
    agent_executor = AgentExecutor(agent=agent, tools=TOOLS)
    response = await agent_executor.ainvoke({'content': context})
    thread_id = response['thread_id']

    return result, thread_id, agent.assistant_id

async def continue_kb_chat(user: TelegramUser, message: str, thread_id, assistant_id):

    agent = OpenAIAssistantRunnable(assistant_id=assistant_id, as_agent=True)
    agent_executor = AgentExecutor(agent=agent, tools=TOOLS)
    response = await agent_executor.ainvoke({'content': message, 'thread_id': thread_id})
    thread_id = response['thread_id']
    output = response['output']

    return output, thread_id, assistant_id


async def generate_csv_from_notes(user: TelegramUser) -> str:
    
    notes = await user.notes.filter(is_vectorized=False).all()
    notes_data = [["message_id", "text"]] + [[note.telegram_message_id, note.text] for note in notes]

    # Generate filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{user.telegram_id}_{timestamp}.csv"

    # Asynchronously write CSV content using aiocsv.AsyncWriter
    async with aiofiles.open(filename, 'w', encoding='utf-8', newline='') as f:
        writer = AsyncWriter(f, quotechar='"', quoting=csv.QUOTE_MINIMAL)
        await writer.writerows(notes_data)

    return filename

async def upload_notes_to_pinecone(user: TelegramUser):

    # Create a txt file with all the not vectorized notes
    filename = await generate_csv_from_notes(user)
    loader = CSVLoader(filename, source_column='message_id', content_columns=['text'])
    documents = loader.load()

    text_splitter = CharacterTextSplitter(chunk_size=1024, chunk_overlap=256)
    docs = text_splitter.split_documents(documents)

    if user.index_name:
        index_name = user.index_name
    else:
        index_name = random.choice(INDEX_NAMES)
        user.index_name = index_name
        await user.save()

    vector_store = await Pinecone.afrom_documents(
        docs,
        index_name=index_name,
        embedding=EMBEDDINGS,
        namespace=user.vector_storage_namespace,
    )

    # Mark notes as vectorized
    await user.notes.filter(is_vectorized=False).update(is_vectorized=True)

    return

async def search_notes(user: TelegramUser, query: str):

    vector_store = Pinecone(
        index_name=user.index_name,
        namespace=user.vector_storage_namespace,
        embedding=EMBEDDINGS
    )

    search_results = await vector_store.asimilarity_search_with_relevance_scores(query=query, k=5)
    # Filter out notes with relevance score less than 0.5. List of Tuples of (doc, similarity_score)
    search_results = [(doc, score) for doc, score in search_results if score > 0.6]
    # Sort by relevance score, return only docs
    search_results = [doc for doc, score in sorted(search_results, key=lambda x: x[1], reverse=True)]

    # Remove duplicates
    unique_search_results = []
    seen_sources = set()
    for doc in search_results:
        if doc.metadata['source'] not in seen_sources:
            unique_search_results.append(doc)
            seen_sources.add(doc.metadata['source'])

    # Update user's queries_count
    user.queries_count += 1
    await user.save()

    return unique_search_results