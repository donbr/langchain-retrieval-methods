# %% [markdown]
# # Introduction
# 
# Welcome to the **LangChain Retrieval Methods** notebook.  
# In this tutorial you will:
# 
# 1. **Load** a small corpus of John Wick movie reviews.
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
# 4. **Visualize** key metrics and response examples to understand trade-offs.
# 
# By the end of the notebook, you’ll know:
# - When to **start simple** (Naive or BM25) versus **scale up** (Ensemble or Semantic).
# - How context-window advances (4 K → 32 K → 128 K) and loader-splitter decoupling shape modern RAG architectures.
# - Practical tips for **production readiness**, including index sharding, zero-downtime reindexes, and drift monitoring.
# 
# > **Prerequisites**  
# > - Python 3.11 environment (see Quickstart)  
# > - Access to a Qdrant and Redis instance (using Docker)  
# > - OpenAI API credentials for embedding & reranking  
# 
# Run the cells in order, or jump to the section that interests you. Let’s get started!  
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

# %%
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm = ChatOpenAI(model="gpt-4.1-mini")
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# %%
from phoenix.otel import register

# configure the Phoenix tracer
tracer_provider = register(
  project_name="my-llm-app", # Default is 'default'
  auto_instrument=True # Auto-instrument your app based on installed OI dependencies
)

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
# ##### TEMPORARY:  Qdrant and Redis Database reset
# 
# - For now I'm doing a data reset before each run (🤷‍♂️ not best practice 🤷‍♀️)
# 
# ```bash
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
baseline_vectorstore = QdrantVectorStore.from_documents(
    all_review_docs,
    embeddings,
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
child_splitter = RecursiveCharacterTextSplitter(chunk_size=200)
parent_document_retriever = ParentDocumentRetriever(
    vectorstore = parent_children_vectorstore,
    docstore=parent_document_store,
    child_splitter=child_splitter,
)

parent_document_retriever.add_documents(all_review_docs)

# %% [markdown]
# ### Level 3: Vector Storage organized by Semantic Chunks

# %%
semantic_chunker = SemanticChunker(
    embeddings,
    breakpoint_threshold_type="percentile"
)

semantic_documents = semantic_chunker.split_documents(all_review_docs)

# %%
semantic_vectorstore = QdrantVectorStore.from_documents(
    semantic_documents,
    embeddings,
    url=QDRANT_API_URL,
    api_key=QDRANT_API_KEY,
    prefer_grpc=True,
    collection_name="johnwick_semantic"
)

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
tracer = tracer_provider.get_tracer(__name__)

# %%
# from langsmith import traceable

# @traceablele(name="naive_retrieval", run_type="chain", metadata={"method":"naive"})
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

# %%
from IPython.display import Markdown, display

# Map of titles to response objects
responses = {
    "Naive Retrieval Chain Response":              naive_retrieval_chain_response,
    "BM25 Retrieval Chain Response":               bm25_retrieval_chain_response,
    "Contextual Compression Chain Response":       contextual_compression_retrieval_chain_response,
    "Multi-Query Retrieval Chain Response":        multi_query_retrieval_chain_response,
    "Parent Document Retrieval Chain Response":    parent_document_retrieval_chain_response,
    "Ensemble Retrieval Chain Response":           ensemble_retrieval_chain_response,
    "Semantic Retrieval Chain Response":           semantic_retrieval_chain_response,
}

for header, resp in responses.items():
    display(Markdown(f"## {header}\n"))
    print("\n")
    print(resp)
    print("\n")


# %% [markdown]
# ### Retrieval Chain validation

# %%
from IPython.display import Markdown, display

# Map of titles to chains
chains = {
    "Naive Retrieval":              naive_retrieval_chain,
    "BM25 Retrieval":               bm25_retrieval_chain,
    "Contextual Compression":       contextual_compression_retrieval_chain,
    "Multi-Query Retrieval":        multi_query_retrieval_chain,
    "Parent Document Retrieval":    parent_document_retrieval_chain,
    "Ensemble Retrieval":           ensemble_retrieval_chain,
    "Semantic Retrieval":           semantic_retrieval_chain,
}

for title, chain in chains.items():
    display(Markdown(f"## {title}\n"))
    print(chain)
    # print(chain.get_graph().draw_ascii())
    print("\n")



