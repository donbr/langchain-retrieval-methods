# %% [markdown]
# # Introduction
# 
# Welcome to the **LangChain Retrieval Methods** notebook with **intelligent data ingestion and workflow orchestration**.  
# In this tutorial you will:
# 
# 1. **Load and ingest** a small corpus of John Wick movie reviews using persistent storage
# 2. **Explore** seven distinct retrieval strategies:
#    - Naive (whole‐document vectors)
#    - BM25 (keyword matching)
#    - Contextual Compression (reranking)
#    - Multi‐Query (query expansion)
#    - Parent Document (hierarchical chunks)
#    - Ensemble (fusion of methods)
#    - Semantic (boundary‐aware chunking)
# 
# 3. **Compare** each method across:
#    - Retrieval **quality** (recall, qualitative response patterns)
#    - **Latency** (ms per query)
#    - **Cost** (API/token usage)
#    - **Resource footprint** (index size & shape)
# 
# 4. **Visualize** key metrics and response examples to understand trade-offs
# 5. **Orchestrate** data workflows using modern infrastructure patterns
# 
# ## 🚀 **Smart Ingestion Pipeline Architecture**
# 
# This notebook implements a **production-ready ingestion strategy** that separates data ingestion from retrieval experiments:
# 
# ### **🏗️ Architecture Overview**
# 
# ```
# ┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
# │   Data Sources  │    │   Orchestration  │    │  Storage Layer  │
# │                 │    │                  │    │                 │
# │ • CSV Files     │───▶│ • Prefect Flows  │───▶│ • Redis (KV)    │
# │ • APIs          │    │ • Schedule Tasks │    │ • Qdrant (Vec)  │
# │ • Documents     │    │ • Error Handling │    │ • PostgreSQL    │
# └─────────────────┘    └──────────────────┘    └─────────────────┘
#          │                        │                        │
#          └────────────────────────┼────────────────────────┘
#                                   ▼
#                         ┌──────────────────┐
#                         │  Retrieval Apps  │
#                         │                  │
#                         │ • RAG Chains     │
#                         │ • Evaluation     │
#                         │ • Monitoring     │
#                         └──────────────────┘
# ```
# 
# ### **🔄 Data Flow Pipeline**
# 
# 1. **📥 Ingestion Phase** (Separate Process)
#    - Load documents from various sources
#    - Apply text splitting and chunking strategies  
#    - Generate embeddings and store in vector databases
#    - Persist parent documents in Redis key-value store
#    - Track metadata and lineage in PostgreSQL
# 
# 2. **⚡ Retrieval Phase** (Runtime)
#    - Connect to existing data stores
#    - Run retrieval experiments without re-ingesting
#    - Compare different strategies on the same dataset
#    - Monitor performance with Phoenix observability
# 
# ### **💡 Key Benefits of This Approach**
# 
# | Benefit | Description |
# |---------|-------------|
# | **🔄 Persistent Storage** | Data survives notebook restarts - no re-ingestion needed |
# | **⚡ Fast Iterations** | Experiment with different retrieval methods quickly |
# | **🎯 Consistent Datasets** | Same data across all experiments ensures fair comparisons |
# | **📊 Production Ready** | Mimics real-world deployment patterns |
# | **🛠️ Modular Design** | Ingestion and retrieval can be scaled independently |
# | **🔍 Observability** | Full tracing and monitoring with Phoenix + Prefect |
# 
# ## 🎯 **Getting Started: Ingestion Strategy Guide**
# 
# ### **Prerequisites**
# 
# **Infrastructure (via Docker Compose):**
# ```bash
# # Start all services
# docker compose up -d
# 
# # Verify services are running
# docker compose ps
# ```
# 
# **Required Services:**
# - **Qdrant** (Vector Database): `http://localhost:6333`
# - **Redis** (Key-Value Store): `localhost:6379`  
# - **PostgreSQL** (Metadata): `localhost:5432`
# - **Phoenix** (Observability): `http://localhost:6006`
# - **Prefect** (Orchestration): `http://localhost:4200`
# - **MinIO** (Object Storage): `http://localhost:9001`
# 
# **Environment Setup:**
# - Python 3.11+ environment
# - OpenAI API credentials for embedding & reranking
# - Qdrant Cloud credentials (optional - can use local Docker)
# 
# ### **🔧 Ingestion Workflow Options**
# 
# This notebook supports **three ingestion approaches**:
# 
# #### **Option 1: Smart Notebook Ingestion (Current)**
# ```python
# # Automatic data detection and reuse - perfect for learning!
# if not data_exists:
#     parent_document_retriever.add_documents(all_review_docs)
# else:
#     print("✅ Using existing data!")
# ```
# **✅ Best for:** Learning, experimentation, rapid iteration
# 
# #### **Option 2: Standalone Scripts**
# ```bash
# # Separate ingestion from retrieval
# python ingestion.py --config production.yaml
# jupyter notebook retrieval_experiments.ipynb
# ```
# **✅ Best for:** Controlled workflows, repeatable processes
# 
# #### **Option 3: Prefect Workflow Orchestration**
# ```python
# # Enterprise-grade pipeline with monitoring & retries
# prefect deployment run 'rag-ingestion-pipeline/production'
# ```
# **✅ Best for:** Production deployments, enterprise reliability
# 
# > **📖 For Production Deployments**  
# > See our comprehensive [Ingestion Pipeline Strategy Guide](docs/ingestion_pipeline_strategy.md) for:
# > - Detailed Prefect integration research & trade-offs
# > - Production implementation patterns  
# > - Enterprise deployment strategies
# > - Complete code examples and best practices
# 
# By the end of this notebook, you'll understand:
# - **When to start simple** (Naive or BM25) versus **scale up** (Ensemble or Semantic)
# - **How persistent storage** accelerates development and ensures consistency
# - **Modern deployment patterns** for production RAG systems
# - **Integration strategies** for monitoring, observability, and workflow management
# 
# > **✨ New: Smart Persistent Storage**  
# > This notebook features **intelligent data persistence**! Data is automatically saved to Redis and Qdrant and reused between runs for faster iterations. No more waiting for re-ingestion!
# 
# Run the cells in order, or jump to the section that interests you. Let's get started!  
# 

# %% [markdown]
# ## ☕ 📴 🔥 TLDR ☕ 📴 🔥
# 
# | Action | Command |
# |---|---|
# | ☕ Morning Coffee Startup | `docker compose up -d` |
# | 📴 That's a Wrap | `docker compose down` |
# | 🔥 Burn It All Down | `docker compose down --volumes --rmi all` |

# %% [markdown]
# ## Foundation: Docker Containers for Qdrant, Redis, Postgres, and Arize Phoenix (oh my!)
# 
# - use Docker Compose to setup containers
# - Draft [Docker Admin Guide](docs/docker-admin-guide.md)
# - [the `docker-compose.yml file is located here](docker-compose.yml)
# 
# | Action | Command |
# |---|---|
# | Start containers | `docker compose up -d` |
# | Stop containers | `docker compose down` |
# | Stop containers - remove volumes, images | `docker compose down --volumes --rmi all` |
# 
# - the last option is great for resets and starting from scratch

# %% [markdown]
# ## 🔧 Environment Configuration & API Setup

# %%
from pathlib import Path
import requests
from dotenv import load_dotenv
import os

import os
from datetime import datetime
from phoenix.otel import register

load_dotenv()

# Build a dynamic project name (e.g. include timestamp)
project_name = f"retrieval-method-comparison-{datetime.now().strftime('%Y%m%d_%H%M%S')}"

os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY')
os.environ["COHERE_API_KEY"] = os.getenv('COHERE_API_KEY')

# os.environ["LANGSMITH_TRACING"] = "true"
# os.environ["LANGSMITH_PROJECT"] = project_name
# os.environ["LANGSMITH_API_KEY"] = os.getenv('LANGSMITH_API_KEY')

QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_API_URL = os.getenv("QDRANT_API_URL")

os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")

# configure the Phoenix tracer
tracer_provider = register(
  project_name=project_name,
  auto_instrument=True # Auto-instrument your app based on installed OI dependencies
)

# %%
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm = ChatOpenAI(model="gpt-4.1-mini")
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# %%
# from langchain_core.prompts import ChatPromptTemplate
# from langchain_openai import ChatOpenAI

# prompt = ChatPromptTemplate.from_template("{x} {y} {z}?").partial(x="why is", z="blue")
# chain = prompt | llm
# chain.invoke(dict(y="sky"))

# %%
from phoenix.otel import register

# This single call auto-instruments ALL LangChain components
tracer_provider = register(
    project_name=project_name,
    auto_instrument=True  # Automatically traces LangChain chains, retrievers, LLMs, etc.
)

# print(f"✅ Phoenix auto-instrumentation enabled for project: {project_name}")
# print("🔍 Phoenix will automatically capture all LangChain component traces")

# %%
from langchain_core.prompts import ChatPromptTemplate

RAG_TEMPLATE = """\
You are a helpful and kind assistant. Use the context provided below to answer the question.

If you do not know the answer, or are unsure, say you don't know.

Query:
{question}

Context:
{context}
"""

rag_prompt = ChatPromptTemplate.from_template(RAG_TEMPLATE)

# %% [markdown]
# ## 📊 Dataset Loading & Preprocessing for RAG

# %% [markdown]
# ##### ✅ PERSISTENT DATA STORAGE
# 
# **This notebook now uses persistent data storage!**
# 
# - 💾 **Redis & Qdrant data persists** between notebook runs
# - ⚡ **Faster restarts** - no need to re-ingest data every time  
# - 🔄 **Automatic detection** - notebook checks for existing data
# - 🗑️ **Manual reset option** - use the reset utility above when needed
# 
# **Previous approach (manual reset before each run):**
# ```bash
# # Only run these commands if you want to start fresh:
# docker compose stop qdrant redis
# docker compose rm -f qdrant redis
# docker volume rm langchain-retrieval-methods_qdrant_data langchain-retrieval-methods_redis_data
# docker compose up -d qdrant redis
# ```

# %%
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

# %%
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

# %% [markdown]
# ## 🏗️ Building RAG Infrastructure: Storage

# %% [markdown]
# ### 🔧 Data Management Utilities
# 
# The notebook now supports **persistent data storage** - data is automatically saved to Redis and Qdrant and reused between runs.
# 
# **Key Benefits:**
# - ⚡ **Fast restarts** - no need to re-ingest data every time
# - 🔄 **Consistent experiments** - same data across multiple runs  
# - 💾 **Persistent storage** - survives notebook restarts
# 
# **Data Management Options:**
# 
# | Scenario | Command |
# |----------|---------|
# | 🚀 **First Run** | Just run the notebook - data will be ingested automatically |
# | 🔄 **Subsequent Runs** | Data will be detected and reused automatically |
# | 🗑️ **Force Fresh Data** | Run the reset command below, then continue with notebook |
# | 📊 **Check Data Status** | The notebook will show data status before each operation |

# %%
def reset_data_stores():
    """
    🗑️ DANGER ZONE: Reset all persistent data stores
    
    This will:
    - Clear all Redis data (parent documents)
    - Clear all Qdrant collections (child chunks) 
    - Force fresh ingestion on next run
    
    Only run this if you want to start completely fresh!
    """
    import subprocess
    import sys
    
    print("🚨 WARNING: This will delete ALL data in Redis and Qdrant!")
    response = input("Type 'RESET' to confirm deletion: ")
    
    if response == "RESET":
        try:
            # Stop containers, remove volumes, restart
            commands = [
                "docker compose stop redis qdrant",
                "docker compose rm -f redis qdrant", 
                "docker volume rm langchain-retrieval-methods_redis_data langchain-retrieval-methods_qdrant_data",
                "docker compose up -d redis qdrant"
            ]
            
            for cmd in commands:
                print(f"Running: {cmd}")
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"⚠️  Command failed: {result.stderr}")
                else:
                    print(f"✅ {cmd}")
            
            print("✅ Data stores reset successfully!")
            print("🔄 Continue with the notebook - fresh data will be ingested.")
            
        except Exception as e:
            print(f"❌ Reset failed: {e}")
            print("💡 Try running the Docker commands manually.")
    else:
        print("❌ Reset cancelled - data preserved.")

# Uncomment the line below ONLY if you want to reset all data:
# reset_data_stores()

# %%
from langchain_qdrant import QdrantVectorStore  # Updated import
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient, models
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain.retrievers import ParentDocumentRetriever
from langchain_community.storage import RedisStore
from langchain.storage import create_kv_docstore

# %% [markdown]
# ### Level 1: Simple Vector Storage (Baseline)
# 
# - creates the vector store using the all_review_docs Document object

# %%
def check_baseline_data_exists():
    """Check if baseline Qdrant collection already has data"""
    try:
        if not cloud_client.collection_exists("johnwick_baseline"):
            print("📭 Baseline collection doesn't exist yet.")
            return False
            
        count = cloud_client.count(collection_name="johnwick_baseline").count
        print(f"📊 Baseline collection: {count} vectors")
        
        exists = count > 0
        if exists:
            print("✅ Baseline data found!")
        else:
            print("📭 Baseline collection exists but is empty.")
            
        return exists
        
    except Exception as e:
        print(f"⚠️  Error checking baseline data: {e}")
        return False

# Check for existing baseline data
baseline_data_exists = check_baseline_data_exists()

if not baseline_data_exists:
    print("🔄 Creating baseline vectorstore with fresh data...")
    print(f"📄 Processing {len(all_review_docs)} documents...")
    
    baseline_vectorstore = QdrantVectorStore.from_documents(
        all_review_docs,
        embeddings,
        url=QDRANT_API_URL,
        api_key=QDRANT_API_KEY,
        prefer_grpc=True,
        collection_name="johnwick_baseline"
    )
    
    # Verify creation
    final_count = cloud_client.count(collection_name="johnwick_baseline").count
    print(f"✅ Baseline vectorstore created with {final_count} vectors!")
else:
    print("✅ Using existing baseline vectorstore!")
    
    # Connect to existing vectorstore
    baseline_vectorstore = QdrantVectorStore(
        embedding=embeddings,
        url=QDRANT_API_URL,
        api_key=QDRANT_API_KEY,
        prefer_grpc=True,
        collection_name="johnwick_baseline"
    )

# %% [markdown]
# ### Level 2: Hierarchical Storage (Parent-Child Architecture)

# %% [markdown]
# #### Parent Documents: Redis Key-Value Store

# %%
redis_byte_store = RedisStore(redis_url="redis://localhost:6379")
parent_document_store = create_kv_docstore(redis_byte_store)

# %% [markdown]
# #### Child Records: Qdrant Vector Embeddings

# %%
# Initialize Qdrant client
cloud_client = QdrantClient(
    url=QDRANT_API_URL,
    api_key=QDRANT_API_KEY,
    prefer_grpc=True
)

# Check if the Qdrant collection exists
if not cloud_client.collection_exists("johnwick_parent_children"):
    cloud_client.create_collection(
        collection_name="johnwick_parent_children",
        vectors_config=models.VectorParams(
            size=1536,
            distance=models.Distance.COSINE
        ),
    )

# Construct the VectorStore using cloud client
parent_children_vectorstore = QdrantVectorStore(
    embedding=embeddings,
    client=cloud_client,
    collection_name="johnwick_parent_children",
)

# %% [markdown]
# #### Parent Document Retriever definition

# %%
def check_data_exists():
    """Check if data already exists in Redis and Qdrant stores"""
    try:
        # Check Redis for parent documents
        redis_keys = list(parent_document_store.yield_keys())
        redis_count = len(redis_keys)
        
        # Check Qdrant for child chunks
        qdrant_count = cloud_client.count(collection_name="johnwick_parent_children").count
        
        print(f"📊 Data Store Status:")
        print(f"   Redis (parent docs): {redis_count} documents")
        print(f"   Qdrant (child chunks): {qdrant_count} vectors")
        
        data_exists = redis_count > 0 and qdrant_count > 0
        
        if data_exists:
            print("✅ Existing data found in both stores!")
        else:
            print("📭 No existing data found - will need to ingest.")
            
        return data_exists
        
    except Exception as e:
        print(f"⚠️  Error checking data: {e}")
        return False

# Check for existing data
data_exists = check_data_exists()

# %%
child_splitter = RecursiveCharacterTextSplitter(chunk_size=200)
parent_document_retriever = ParentDocumentRetriever(
    vectorstore = parent_children_vectorstore,
    docstore=parent_document_store,
    child_splitter=child_splitter,
)

# Conditional data ingestion - only add documents if they don't already exist
if not data_exists:
    print("🔄 No existing data found. Populating data stores...")
    print(f"📄 Ingesting {len(all_review_docs)} documents...")
    
    parent_document_retriever.add_documents(all_review_docs)
    
    # Verify ingestion was successful
    final_check = check_data_exists()
    if final_check:
        print("✅ Data ingestion completed successfully!")
    else:
        print("❌ Data ingestion may have failed - please check stores.")
else:
    print("✅ Using existing data from Redis and Qdrant stores!")
    print("💡 To force re-ingestion, restart Docker containers or clear the stores.")

# %%
# Validate that retriever can access the data
def validate_retriever():
    """Test that the retriever can successfully query the data"""
    try:
        test_query = "test query"
        # Just test the vectorstore search to ensure child chunks are accessible
        test_results = parent_children_vectorstore.similarity_search(test_query, k=1)
        
        if len(test_results) > 0:
            # Check if parent documents are accessible via the child's doc_id
            child_doc = test_results[0]
            doc_id = child_doc.metadata.get('doc_id')
            
            if doc_id:
                parent_doc = parent_document_store.mget([doc_id])
                if parent_doc and parent_doc[0]:
                    print("✅ Retriever validation successful - can access both child chunks and parent documents!")
                    return True
                else:
                    print("⚠️  Child chunks found but parent document retrieval failed!")
                    return False
            else:
                print("⚠️  Child chunks found but missing doc_id metadata!")
                return False
        else:
            print("⚠️  No child chunks found in vectorstore!")
            return False
            
    except Exception as e:
        print(f"❌ Retriever validation failed: {e}")
        return False

# Validate the retriever setup
retriever_ready = validate_retriever()

if not retriever_ready:
    print("💡 If validation failed, try restarting with fresh data stores.")

# %% [markdown]
# ### 📊 Data Store Infrastructure Summary

# %%
def show_data_infrastructure_summary():
    """Display a comprehensive summary of all data stores"""
    print("=" * 60)
    print("📊 DATA INFRASTRUCTURE SUMMARY")
    print("=" * 60)
    
    # Baseline Vectorstore
    try:
        baseline_count = cloud_client.count(collection_name="johnwick_baseline").count
        baseline_status = "✅ Ready" if baseline_count > 0 else "❌ Empty"
    except:
        baseline_status = "❌ Error"
        baseline_count = 0
    
    # Parent-Child Architecture
    try:
        redis_count = len(list(parent_document_store.yield_keys()))
        redis_status = "✅ Ready" if redis_count > 0 else "❌ Empty"
        
        parent_child_count = cloud_client.count(collection_name="johnwick_parent_children").count
        parent_child_status = "✅ Ready" if parent_child_count > 0 else "❌ Empty"
    except:
        redis_status = "❌ Error"
        parent_child_status = "❌ Error"
        redis_count = 0
        parent_child_count = 0
    
    # Semantic Vectorstore
    try:
        semantic_count = cloud_client.count(collection_name="johnwick_semantic").count
        semantic_status = "✅ Ready" if semantic_count > 0 else "❌ Empty"
    except:
        semantic_status = "❌ Error"
        semantic_count = 0
    
    print(f"🎯 Baseline Vectorstore:        {baseline_status:12} ({baseline_count:4} vectors)")
    print(f"📦 Redis Parent Store:          {redis_status:12} ({redis_count:4} documents)")
    print(f"🔍 Qdrant Child Chunks:         {parent_child_status:12} ({parent_child_count:4} vectors)")
    print(f"🧠 Semantic Vectorstore:        {semantic_status:12} ({semantic_count:4} vectors)")
    
    print("-" * 60)
    
    all_ready = all([
        baseline_count > 0,
        redis_count > 0, 
        parent_child_count > 0,
        semantic_count > 0
    ])
    
    if all_ready:
        print("🎉 ALL DATA STORES READY - You can proceed with retrieval experiments!")
    else:
        print("⚠️  Some data stores are not ready. Check the status above.")
    
    print("=" * 60)

# Show the infrastructure summary
show_data_infrastructure_summary()

# %% [markdown]
# ### Level 3: Vector Storage organized by Semantic Chunks

# %%
def check_semantic_data_exists():
    """Check if semantic Qdrant collection already has data"""
    try:
        if not cloud_client.collection_exists("johnwick_semantic"):
            print("📭 Semantic collection doesn't exist yet.")
            return False
            
        count = cloud_client.count(collection_name="johnwick_semantic").count
        print(f"📊 Semantic collection: {count} vectors")
        
        exists = count > 0
        if exists:
            print("✅ Semantic data found!")
        else:
            print("📭 Semantic collection exists but is empty.")
            
        return exists
        
    except Exception as e:
        print(f"⚠️  Error checking semantic data: {e}")
        return False

# Check for existing semantic data
semantic_data_exists = check_semantic_data_exists()

if not semantic_data_exists:
    print("🔄 Creating semantic chunks and vectorstore...")
    
    semantic_chunker = SemanticChunker(
        embeddings,
        breakpoint_threshold_type="percentile"
    )
    
    print(f"📄 Processing {len(all_review_docs)} documents with semantic chunking...")
    semantic_documents = semantic_chunker.split_documents(all_review_docs)
    print(f"📊 Created {len(semantic_documents)} semantic chunks")
    
    semantic_vectorstore = QdrantVectorStore.from_documents(
        semantic_documents,
        embeddings,
        url=QDRANT_API_URL,
        api_key=QDRANT_API_KEY,
        prefer_grpc=True,
        collection_name="johnwick_semantic"
    )
    
    # Verify creation
    final_count = cloud_client.count(collection_name="johnwick_semantic").count
    print(f"✅ Semantic vectorstore created with {final_count} vectors!")
    
else:
    print("✅ Using existing semantic vectorstore!")
    
    # Connect to existing vectorstore  
    semantic_vectorstore = QdrantVectorStore(
        embedding=embeddings,
        url=QDRANT_API_URL,
        api_key=QDRANT_API_KEY,
        prefer_grpc=True,
        collection_name="johnwick_semantic"
    )
    
    # Note: We don't recreate semantic_documents as they're not needed for retrieval
    print("💡 Note: Semantic chunks are stored in Qdrant - no need to recreate in memory.")

# %% [markdown]
# ## 🎯 Core Learning: 7 Retrieval Strategies

# %% [markdown]
# ### Strategy Setup: Tracing & Monitoring

# %%
# # setup langsmith tracing

# from langsmith import Client, traceable

# langsmith_client = Client()

# %% [markdown]
# ### Strategy 1: Naive Retrieval (Baseline)

# %%
from langchain_core.runnables import RunnablePassthrough
from operator import itemgetter
from langchain_core.output_parsers import StrOutputParser

naive_retriever = baseline_vectorstore.as_retriever(search_kwargs={"k" : 10})

naive_retrieval_chain = (
    {"context": itemgetter("question") | naive_retriever, "question": itemgetter("question")}
    | RunnablePassthrough.assign(context=itemgetter("context"))
    | {"response": rag_prompt | llm, "context": itemgetter("context")}
)

# %% [markdown]
# ### Strategy 2: BM25 Retrieval (Keyword-Based)

# %%
from langchain_community.retrievers import BM25Retriever

bm25_retriever = BM25Retriever.from_documents(all_review_docs)

bm25_retrieval_chain = (
    {"context": itemgetter("question") | bm25_retriever, "question": itemgetter("question")}
    | RunnablePassthrough.assign(context=itemgetter("context"))
    | {"response": rag_prompt | llm, "context": itemgetter("context")}
)

# %% [markdown]
# ### Strategy 3: Contextual Compression (AI Reranking)

# %%
from langchain.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_cohere import CohereRerank

compressor = CohereRerank(model="rerank-english-v3.0")

compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=naive_retriever
)

# %%
contextual_compression_retrieval_chain = (
    {"context": itemgetter("question") | compression_retriever, "question": itemgetter("question")}
    | RunnablePassthrough.assign(context=itemgetter("context"))
    | {"response": rag_prompt | llm, "context": itemgetter("context")}
)

# %% [markdown]
# ### Strategy 4: Multi-Query Retrieval (Query Expansion)
# 
# 

# %%
from langchain.retrievers.multi_query import MultiQueryRetriever

multi_query_retriever = MultiQueryRetriever.from_llm(
    retriever=naive_retriever,
    llm=llm
)

# %%
multi_query_retrieval_chain = (
    {"context": itemgetter("question") | multi_query_retriever, "question": itemgetter("question")}
    | RunnablePassthrough.assign(context=itemgetter("context"))
    | {"response": rag_prompt | llm, "context": itemgetter("context")}
)

# %% [markdown]
# ### Strategy 5: Parent Document Retrieval (Hierarchical)

# %%
parent_document_retrieval_chain = (
    {"context": itemgetter("question") | parent_document_retriever, "question": itemgetter("question")}
    | RunnablePassthrough.assign(context=itemgetter("context"))
    | {"response": rag_prompt | llm, "context": itemgetter("context")}
)

# %% [markdown]
# ### Strategy 6: Ensemble Retrieval (Combined Methods)

# %%
from langchain.retrievers import EnsembleRetriever

retriever_list = [bm25_retriever, naive_retriever, parent_document_retriever, compression_retriever, multi_query_retriever]

equal_weighting = [1/len(retriever_list)] * len(retriever_list)

ensemble_retriever = EnsembleRetriever(
    retrievers=retriever_list,
    weights=equal_weighting
)

ensemble_retrieval_chain = (
    {"context": itemgetter("question") | ensemble_retriever, "question": itemgetter("question")}
    | RunnablePassthrough.assign(context=itemgetter("context"))
    | {"response": rag_prompt | llm, "context": itemgetter("context")}
)

# %% [markdown]
# ### Strategy 7: Semantic Retrieval (Semantic Chunking)

# %%
semantic_retriever = semantic_vectorstore.as_retriever(search_kwargs={"k" : 10})

semantic_retrieval_chain = (
    {"context": itemgetter("question") | semantic_retriever, "question": itemgetter("question")}
    | RunnablePassthrough.assign(context=itemgetter("context"))
    | {"response": rag_prompt | llm, "context": itemgetter("context")}
)

# %% [markdown]
# ## 📈 Performance Monitoring & Evaluation Setup

# %%
# setup Arize Phoenix tracing

tracer = tracer_provider.get_tracer(__name__)

# %%
@tracer.chain
def trace_naive_retrieval(question: str):
    try:
        result = naive_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

# @traceable(name="bm25_retrieval", run_type="chain", metadata={"method":"bm25"})
@tracer.chain
def trace_bm25_retrieval(question: str):
    try:
        # Use the correct chain variable name here
        res = bm25_retrieval_chain.invoke({"question": question})
        return {
            "response": res["response"].content,
            "context_docs": len(res["context"])
        }
    except Exception as e:
        return {"error": str(e)}

# @traceable(name="contextual_compression", run_type="chain", metadata={"method":"compression"})
@tracer.chain
def trace_contextual_compression(question: str):
    try:
        result = contextual_compression_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

# @traceable(name="multi_query_retrieval", run_type="chain", metadata={"method":"multi_query"})
@tracer.chain
def trace_multi_query_retrieval(question: str):
    try:
        result = multi_query_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

# @traceable(name="parent_document_retrieval", run_type="chain", metadata={"method":"parent_document"})
@tracer.chain
def trace_parent_document_retrieval(question: str):
    try:
        result = parent_document_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

# @traceable(name="ensemble_retrieval", run_type="chain", metadata={"method":"ensemble"})
@tracer.chain
def trace_ensemble_retrieval(question: str):
    try:
        result = ensemble_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

# @traceable(name="semantic_retrieval", run_type="chain", metadata={"method":"semantic"})
@tracer.chain
def trace_semantic_retrieval(question: str):
    try:
        result = semantic_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

print("✅ Traceable wrappers defined")


# %% [markdown]
# ## ⚡ Execution & Real-Time Comparison

# %%
import pandas as pd

question = "Did people generally like John Wick?"

naive_retrieval_chain_response = trace_naive_retrieval(question)["response"]
bm25_retrieval_chain_response = trace_bm25_retrieval(question)["response"]
contextual_compression_retrieval_chain_response = trace_contextual_compression(question)["response"]
multi_query_retrieval_chain_response = trace_multi_query_retrieval(question)["response"]
semantic_retrieval_chain_response = trace_semantic_retrieval(question)["response"]

print("✅ All methods executed with tracing")

# %% [markdown]
# #### Parent Document Retrieval traces
# 
# - broke these two out due to some serialization issues after adopting Redis
# - helped with troubleshooting

# %%
parent_document_retrieval_chain_response = trace_parent_document_retrieval(question)["response"]
ensemble_retrieval_chain_response = trace_ensemble_retrieval(question)["response"]

# %% [markdown]
# ## 📊 Results Analysis & Performance Visualization
# 
# **Arize Phoenix application URL:**  [http://localhost:6006/](http://localhost:6006/)


