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
from phoenix.otel import register

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
# Initialize Qdrant client
qdrant_client = QdrantClient(
    url=QDRANT_API_URL,
    api_key=QDRANT_API_KEY,
    prefer_grpc=True
)

baseline_vectorstore = QdrantVectorStore(
    embedding=embeddings,
    client=qdrant_client,
    collection_name="azurearch_baseline"
)

# Construct the VectorStore using cloud client
parent_children_vectorstore = QdrantVectorStore(
    embedding=embeddings,
    client=qdrant_client,
    collection_name="azurearch_parent_children",
)

semantic_vectorstore = QdrantVectorStore(
    embedding=embeddings,
    client=qdrant_client,
    collection_name="azurearch_semantic"
)

# %% [markdown]
# ### Level 2: Hierarchical Storage (Parent-Child Architecture)

# %% [markdown]
# #### Parent Documents: Redis Key-Value Store

# %%
from langchain_community.storage import RedisStore
from langchain_community.utilities.redis import get_client

redis_client = get_client('redis://localhost:6379')
parent_document_store = RedisStore(client=redis_client)

# %%
# display first 5 documents in parent_document_store
parent_document_store.mget(list(range(5)))


# %% [markdown]
# #### Parent Document Retriever definition

# %%
child_splitter = RecursiveCharacterTextSplitter(chunk_size=200)
parent_document_retriever = ParentDocumentRetriever(
    vectorstore = parent_children_vectorstore,
    docstore=parent_document_store,
    child_splitter=child_splitter
)

# parent_document_retriever.add_documents(all_review_docs)

# %%
# display Qdrant collections

existing = [c.name for c in qdrant_client.get_collections().collections]

print(type(existing))
print(existing)

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


# %%
all_fields = set()
for doc in docs:
    if hasattr(doc, "metadata"):
        all_fields.update(doc.metadata.keys())
    elif isinstance(doc, dict) and "metadata" in doc:
        all_fields.update(doc["metadata"].keys())
    else:
        print(f"Skipping non-Document: {type(doc)}")

# %% [markdown]
# ## 🎯 Core Learning: 7 Retrieval Strategies

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

question = "How does Azure Site Recovery facilitate migration to Azure for SQL Server on Azure Virtual Machines?"

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


