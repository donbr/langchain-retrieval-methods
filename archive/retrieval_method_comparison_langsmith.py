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

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_PROJECT"] = project_name
os.environ["LANGSMITH_API_KEY"] = os.getenv('LANGSMITH_API_KEY')

QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_API_URL = os.getenv("QDRANT_API_URL")

# %%
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm = ChatOpenAI(model="gpt-4.1-mini")
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

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
# setup langsmith tracing

from langsmith import Client, traceable

langsmith_client = Client()

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
from langsmith import traceable

@traceable(name="naive_retrieval", run_type="chain", metadata={"method":"naive"})
def trace_naive_retrieval(question: str):
    try:
        result = naive_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

@traceable(name="bm25_retrieval", run_type="chain", metadata={"method":"bm25"})
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

@traceable(name="contextual_compression", run_type="chain", metadata={"method":"compression"})
def trace_contextual_compression(question: str):
    try:
        result = contextual_compression_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

@traceable(name="multi_query_retrieval", run_type="chain", metadata={"method":"multi_query"})
def trace_multi_query_retrieval(question: str):
    try:
        result = multi_query_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

@traceable(name="parent_document_retrieval", run_type="chain", metadata={"method":"parent_document"})
def trace_parent_document_retrieval(question: str):
    try:
        result = parent_document_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

@traceable(name="ensemble_retrieval", run_type="chain", metadata={"method":"ensemble"})
def trace_ensemble_retrieval(question: str):
    try:
        result = ensemble_retrieval_chain.invoke({"question": question})
        return {
            "response": result["response"].content,
            "context_docs": len(result["context"])
        }
    except Exception as e:
        return {"error": str(e)}

@traceable(name="semantic_retrieval", run_type="chain", metadata={"method":"semantic"})
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

# %%
from langchain_core.tracers.langchain import wait_for_all_tracers

# run after all your traceable calls
wait_for_all_tracers()

# %% [markdown]
# ## 📊 Results Analysis & Performance Visualization

# %%
from langsmith import Client
# Assume langsmith_client is already initialized,
# and `project_name` is set as above.

# 1. Ensure the dataset exists or create it
dataset_name = f"{project_name}_runs_ds"
try:
    dataset = langsmith_client.create_dataset(
        dataset_name=dataset_name,
        description=(
            "All root chain runs from the John Wick retrieval-method notebook, "
            "including method, response, context_docs, tokens, costs, durations, and errors."
        )
    )
    print(f"✅ Created dataset: {dataset.name!r}")
except Exception:
    dataset = langsmith_client.read_dataset(dataset_name=dataset_name)
    print(f"ℹ️  Using existing dataset: {dataset.name!r}")

# 2. Fetch all top-level chain runs for the project
runs = list(langsmith_client.list_runs(
    project_name=project_name,
    is_root=True,
    run_type="chain",
))

# 3. Ingest each run as an Example in the dataset
for run in runs:
    langsmith_client.create_example_from_run(
        run=run,
        dataset_id=dataset.id
    )

print(f"🚀 Added {len(runs)} runs to dataset {dataset.name!r}")


# %% [markdown]
# ### View LangGraph Dataset

# %%
print(f"🔗 View your dataset: {dataset.url}")

# %% [markdown]
# ### Upload Custom Dataset

# %%
import pandas as pd
from IPython.display import display, Markdown
from datetime import timezone, datetime, timedelta

# Fetch all top-level chain runs for our project
runs = list(langsmith_client.list_runs(
    project_name=project_name,
    is_root=True,
    run_type="chain",
    start_time=datetime.now(timezone.utc) - timedelta(hours=1)  # last hour
))

# Build a record per run, pulling in every field “as is”
records = []
for run in runs:
    records.append({
        "run_id":          str(run.id),
        "name":             run.name,
        "method":           run.metadata.get("method"),
        "status":           run.status,
        "start_time":       run.start_time,
        "end_time":         run.end_time,
        "duration_ms":      ((run.end_time - run.start_time).total_seconds()*1000)
                              if run.start_time and run.end_time else None,
        # cost & tokens
        "prompt_tokens":    run.prompt_tokens,
        "completion_tokens":run.completion_tokens,
        "total_tokens":     run.total_tokens,
        "prompt_cost":      run.prompt_cost,
        "completion_cost":  run.completion_cost,
        "total_cost":       run.total_cost,
        # errors
        "error":            run.error,                                   
        "wrapper_error":    (run.outputs or {}).get("error"),
        # wrapper outputs
        "response":         (run.outputs or {}).get("response"),
        "context_docs":     (run.outputs or {}).get("context_docs"),
    })

df_runs = pd.DataFrame.from_records(records)

# %% [markdown]
# ## 🎯 Core Learning: 7 Retrieval Results

# %%
display(df_runs)

# %% [markdown]
# ### Upload Retrieval Results

# %%
# 1) Create or load the dataset
dataset_name = f"{project_name}_runs_custom_ds"
try:
    dataset = langsmith_client.create_dataset(
        dataset_name=dataset_name,
        description=(
            "All root chain runs from the John Wick retrieval-method notebook, "
            "capturing inputs, outputs, tokens, costs, duration, and errors."
        )
    )
    print(f"✅ Created dataset {dataset.name!r}")
except Exception:
    dataset = langsmith_client.read_dataset(dataset_name=dataset_name)
    print(f"ℹ️  Using existing dataset {dataset.name!r}")

# 2) Bulk‐ingest each run as an Example
for _, row in df_runs.iterrows():
    langsmith_client.create_example(
        dataset_id=dataset.id,
        inputs={
            "run_id": row["run_id"],
            "method": row["method"],
        },
        outputs={
            # include whichever outputs you care about:
            "response": row["response"],
            "context_docs": int(row["context_docs"]),
        },
        metadata={
            # include metrics & error info as metadata
            "status": row["status"],
            "duration_ms": float(row["duration_ms"]),
            "prompt_tokens": int(row["prompt_tokens"]),
            "completion_tokens": int(row["completion_tokens"]),
            "total_tokens": int(row["total_tokens"]),
            "prompt_cost": float(row["prompt_cost"]),
            "completion_cost": float(row["completion_cost"]),
            "total_cost": float(row["total_cost"]),
            # optionally include error
            **({"error": row["error"]} if pd.notna(row.get("error")) else {}),
            **({"wrapper_error": row["wrapper_error"]} if pd.notna(row.get("wrapper_error")) else {}),
        }
    )
print(f"✅ Added {len(df_runs)} runs to dataset {dataset.name!r}")
print("🔗 Dataset URL:", dataset.url)


# %% [markdown]
# ## 🛠️ Exploration Tools & Cleanup Functions

# %% [markdown]
# ### List of Qdrant collections

# %%
# display Qdrant collections

existing = [c.name for c in cloud_client.get_collections().collections]

print(type(existing))
print(existing)

# %% [markdown]
# ### Qdrant info by Storage Type

# %%
# display Qdrant vector store collection metadata

stores = {
    "baseline": baseline_vectorstore,
    "parent":  parent_children_vectorstore,
    "semantic": semantic_vectorstore,
}

for name, vs in stores.items():
    client = vs.client
    col    = vs.collection_name
    print(f"=== {name} ===")
    # 1) Existence check
    print("Exists?      ", client.collection_exists(col))
    # 2) Point count
    print("Point count: ", client.count(collection_name=col))
    # 3) Full collection info
    desc   = client.get_collection(collection_name=col)
    params = desc.config.params

    # — Vector dims & metric
    vec_field = params.vectors
    if isinstance(vec_field, dict):
        # multi-vector mode: pick the first VectorParams
        vp = next(iter(vec_field.values()))
    else:
        # single-vector mode: vectors is itself a VectorParams
        vp = vec_field
    print("Dim / metric:", vp.size, "/", vp.distance)

    # — Shard count & replication factor live on params
    print("Shards / repl:", params.shard_number, "/", params.replication_factor)

    print()


# %% [markdown]
# ### Redis info for Parent Document Store

# %%


# Assume `parent_document_store` already has docs via ParentDocumentRetriever
#  (i.e. you already did retriever.add_documents(...) or similar)

# 1) List all stored keys (document IDs)
all_keys = list(parent_document_store.yield_keys())
print(f"Total documents in store: {len(all_keys)}")
# print("Document IDs:", all_keys)

# 2) Fetch all Document objects
docs = parent_document_store.mget(all_keys)

# 3) Examine metadata schema
#    Collect all metadata field names across docs
all_fields = set()
for doc in docs:
    all_fields.update(doc.metadata.keys())

print(f"Metadata fields present: {sorted(all_fields)}")

# 4) Show per-field value types and a sample value
field_types = {field: set() for field in all_fields}
for doc in docs:
    for field, val in doc.metadata.items():
        field_types[field].add(type(val).__name__)

print("Metadata field types:")
for field, types in field_types.items():
    sample = next((d.metadata[field] for d in docs if field in d.metadata), None)
    print(f" • {field}: types={sorted(types)}, sample={sample!r}")

# 5) (Optional) Print out first N docs’ text lengths to gauge “dimensions”
for i, doc in enumerate(docs[:5], 1):
    text_len = len(doc.page_content)
    print(f"Doc {i} (ID={all_keys[i-1]}): {text_len} characters")


# %% [markdown]
# ### Delete Qdrant collections

# %%
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Distance, VectorParams

# initialize client (cloud or on-prem)
cloud_client = QdrantClient(
    url=QDRANT_API_URL,
    api_key=QDRANT_API_KEY,
    prefer_grpc=True,
)

# create conditional deletion flag
delete_collection = False

if delete_collection:
    # list of collections to drop
    collections_to_reset = [
        "johnwick_baseline",
        "johnwick_parent_children",
        "johnwick_semantic",
    ]

    for col_name in collections_to_reset:
        # guard against missing collections
        if cloud_client.collection_exists(col_name):
            cloud_client.delete_collection(
                collection_name=col_name,
                timeout=60,  # seconds
            )
            print(f"Deleted collection: {col_name}")
        else:
            print(f"Collection not found (skipped): {col_name}")


# %% [markdown]
# ### Response Object validation

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



