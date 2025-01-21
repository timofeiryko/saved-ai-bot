import os
from dotenv import load_dotenv
from pinecone import Pinecone
from backend import INDEX_NAMES  # Replace 'backend' with the actual module name

# Load environment variables
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

# Initialize Pinecone
pc = Pinecone(
    api_key=PINECONE_API_KEY,
)

INDEXES = pc.list_indexes()
INDEXES = [index['name'] for index in INDEXES]

def delete_all_records(index_names):
    for index_name in index_names:
        index = pc.Index(index_name)
        stats = index.describe_index_stats()
        namespaces = stats['namespaces'].keys()
        for namespace in namespaces:
            index.delete(namespace=namespace, delete_all=True)

if __name__ == "__main__":
    delete_all_records(INDEX_NAMES)
