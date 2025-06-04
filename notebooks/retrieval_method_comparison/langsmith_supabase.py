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

SUPABASE_URL=os.getenv("SUPABASE_URL")

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_PROJECT"] = project_name
os.environ["LANGSMITH_API_KEY"] = os.getenv('LANGSMITH_API_KEY')

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
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain.retrievers import ParentDocumentRetriever
from langchain_community.storage import RedisStore
from langchain.storage import create_kv_docstore

from langchain_community.vectorstores import SupabaseVectorStore
from supabase.client import Client, create_client

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# %% [markdown]
# ### Level 1: Simple Vector Storage (Baseline)
# 
# - creates the vector store using the all_review_docs Document object

# %%
baseline_vectorstore = SupabaseVectorStore.from_documents(
    all_review_docs,
    embeddings,
    client=supabase,
    table_name="johnwick_baseline_documents",
    query_name="match_johnwick_baseline_documents",
)

# %% [markdown]
# ### Level 3: Vector Storage organized by Semantic Chunks

# %%
semantic_chunker = SemanticChunker(
    embeddings,
    breakpoint_threshold_type="percentile"
)

semantic_documents = semantic_chunker.split_documents(all_review_docs)

# %%
semantic_vectorstore = SupabaseVectorStore.from_documents(
    semantic_documents,
    embeddings,
    client=supabase,
    table_name="johnwick_semantic_documents",
    query_name="match_johnwick_semantic_documents",
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
# ### Strategy 6: Ensemble Retrieval (Combined Methods)

# %%
from langchain.retrievers import EnsembleRetriever

retriever_list = [bm25_retriever, naive_retriever, compression_retriever, multi_query_retriever]

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
ensemble_retrieval_chain_response = trace_ensemble_retrieval(question)["response"]

print("✅ All methods executed with tracing")

# %%
from langchain_core.tracers.langchain import wait_for_all_tracers

# run after all your traceable calls
wait_for_all_tracers()


