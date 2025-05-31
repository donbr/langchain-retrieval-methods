from pathlib import Path
import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient, models
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain.retrievers import ParentDocumentRetriever
from langchain_community.storage import RedisStore
from langchain.storage import create_kv_docstore
from phoenix.otel import register

load_dotenv()

os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")

# Build a dynamic project name (e.g. include timestamp)
project_name = f"retrieval-method-comparison-{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# configure the Phoenix tracer
tracer_provider = register(
  project_name=project_name,
  auto_instrument=True # Auto-instrument your app based on installed OI dependencies
)

os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY')
os.environ["COHERE_API_KEY"] = os.getenv('COHERE_API_KEY')

# QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_API_URL = os.getenv("QDRANT_API_URL")

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# Set up a consistent data directory in the user's home directory
from pathlib import Path
DATA_DIR = Path.cwd() / "data"
DATA_DIR.mkdir(exist_ok=True)

# URLs and filenames
urls = [
    ("https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw1.csv", "john_wick_1.csv"),
    ("https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw2.csv", "john_wick_2.csv"),
    ("https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw3.csv", "john_wick_3.csv"),
    ("https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw4.csv", "john_wick_4.csv"),
]

# Download files if not already present
for url, fname in urls:
    file_path = DATA_DIR / fname
    if not file_path.exists():
        print(f"Downloading {fname}...")
        r = requests.get(url)
        r.raise_for_status()
        file_path.write_bytes(r.content)
    else:
        print(f"{fname} already exists.")

from langchain_community.document_loaders.csv_loader import CSVLoader
from datetime import datetime, timedelta

all_review_docs = []

for i in range(1, 5):
    loader = CSVLoader(
        file_path=(DATA_DIR / f"john_wick_{i}.csv"),
        metadata_columns=["Review_Date", "Review_Title", "Review_Url", "Author", "Rating"]
    )

    movie_docs = loader.load()
    for doc in movie_docs:

        # Add the "Movie Title" (John Wick 1, 2, ...)
        doc.metadata["Movie_Title"] = f"John Wick {i}"

        # convert "Rating" to an `int`, if no rating is provided - assume 0 rating
        doc.metadata["Rating"] = int(doc.metadata["Rating"]) if doc.metadata["Rating"] else 0

        # newer movies have a more recent "last_accessed_at" (store as ISO string)
        doc.metadata["last_accessed_at"] = (datetime.now() - timedelta(days=4-i)).isoformat()

    all_review_docs.extend(movie_docs)

## 🏗️ Building RAG Infrastructure: Storage

### Level 1: Simple Vector Storage (Baseline) 
# creates the vector store using the all_review_docs Document object

baseline_vectorstore = QdrantVectorStore.from_documents(
    all_review_docs,
    embeddings,
    url=QDRANT_API_URL,
    api_key=QDRANT_API_KEY,
    prefer_grpc=True,
    collection_name="johnwick_baseline"
)

### Level 2: Hierarchical Storage (Parent-Child Architecture)

#### Parent Documents: Redis Key-Value Store

redis_byte_store = RedisStore(redis_url="redis://localhost:6379")
parent_document_store = create_kv_docstore(redis_byte_store)

#### Child Records: Qdrant Vector Embeddings

# Initialize Qdrant client
qdrant_client = QdrantClient(
    url=QDRANT_API_URL,
    api_key=QDRANT_API_KEY,
    prefer_grpc=True
)

# Check if the Qdrant collection exists
if not qdrant_client.collection_exists("johnwick_parent_children"):
    qdrant_client.create_collection(
        collection_name="johnwick_parent_children",
        vectors_config=models.VectorParams(
            size=1536,
            distance=models.Distance.COSINE
        ),
    )

# Construct the VectorStore
parent_children_vectorstore = QdrantVectorStore(
    embedding=embeddings,
    client=qdrant_client,
    collection_name="johnwick_parent_children",
)

#### Parent Document Retriever definition

child_splitter = RecursiveCharacterTextSplitter(chunk_size=200)
parent_document_retriever = ParentDocumentRetriever(
    vectorstore = parent_children_vectorstore,
    docstore=parent_document_store,
    child_splitter=child_splitter,
)

parent_document_retriever.add_documents(all_review_docs)

### Level 3: Vector Storage organized by Semantic Chunks

semantic_chunker = SemanticChunker(
    embeddings,
    breakpoint_threshold_type="percentile"
)

semantic_documents = semantic_chunker.split_documents(all_review_docs)

semantic_vectorstore = QdrantVectorStore.from_documents(
    semantic_documents,
    embeddings,
    url=QDRANT_API_URL,
    api_key=QDRANT_API_KEY,
    prefer_grpc=True,
    collection_name="johnwick_semantic"
)
