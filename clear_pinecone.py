from pinecone import Pinecone
from backend import INDEX_NAMES
import os

import dotenv
dotenv.load_dotenv()

pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

for index in INDEX_NAMES:
    pc.delete_index(index)
    print(f"Deleted index: {index}")