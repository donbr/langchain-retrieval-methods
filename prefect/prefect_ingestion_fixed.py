# prefect_ingestion_fixed.py

from pathlib import Path
import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
import json

import prefect
from prefect import flow, task, get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.cache_policies import NO_CACHE

from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient, models
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain.retrievers import ParentDocumentRetriever
from langchain_community.storage import RedisStore
from langchain.storage import create_kv_docstore

# ----------------------------------------
# 1. Load environment variables / constants
# ----------------------------------------
load_dotenv()

os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
os.environ["COHERE_API_KEY"] = os.getenv("COHERE_API_KEY")

QDRANT_API_URL = os.getenv("QDRANT_API_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")  # Make sure this is set

# Where we store the CSVs
DATA_DIR = Path.cwd() / "data"
DATA_DIR.mkdir(exist_ok=True)

# Download CSV URLs if missing
urls = [
    ("https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw1.csv", "john_wick_1.csv"),
    ("https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw2.csv", "john_wick_2.csv"),
    ("https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw3.csv", "john_wick_3.csv"),
    ("https://raw.githubusercontent.com/AI-Maker-Space/DataRepository/main/jw4.csv", "john_wick_4.csv"),
]
for url, fname in urls:
    file_path = DATA_DIR / fname
    if not file_path.exists():
        print(f"Downloading {fname}…")
        r = requests.get(url)
        r.raise_for_status()
        file_path.write_bytes(r.content)
    else:
        print(f"{fname} already exists.")

# ----------------------------------------
# 2. Common "load & preprocess" tasks
# ----------------------------------------

@task(name="load-documents", retries=2, retry_delay_seconds=10)
def load_documents_task(data_dir: str) -> list:
    """
    Load all four CSVs into a single list of Document objects.
    Mirrors your original "for i in range(1,5): loader = CSVLoader…" logic.
    """
    from langchain_community.document_loaders.csv_loader import CSVLoader

    all_docs = []
    for i in range(1, 5):
        loader = CSVLoader(
            file_path=(Path(data_dir) / f"john_wick_{i}.csv"),
            metadata_columns=["Review_Date", "Review_Title", "Review_Url", "Author", "Rating"]
        )
        docs = loader.load()
        for doc in docs:
            doc.metadata["Movie_Title"] = f"John Wick {i}"
            doc.metadata["Rating"] = int(doc.metadata["Rating"]) if doc.metadata["Rating"] else 0
            # Stagger last_accessed_at by (4 - i) days
            doc.metadata["last_accessed_at"] = (datetime.now() - timedelta(days=4 - i)).isoformat()
        all_docs.extend(docs)

    return all_docs


@task(name="create-semantic-chunks", retries=2, retry_delay_seconds=15)
def create_semantic_chunks_task(documents: list) -> list:
    """
    Build semantic chunks from all_docs using the same settings in your original script.
    """
    # Use exactly your original SemanticChunker logic
    # e.g. SemanticChunker(embeddings, breakpoint_threshold_type="percentile")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    semantic_chunker = SemanticChunker(
        embeddings,
        breakpoint_threshold_type="percentile"
    )
    semantic_docs = semantic_chunker.split_documents(documents)
    return semantic_docs


# ----------------------------------------
# 3. Infrastructure setup tasks
# ----------------------------------------

@task(
    name="setup-redis-store",
    retries=3,
    retry_delay_seconds=10,
    cache_key_fn=None  # NO_CACHE
)
def setup_redis_store_task(redis_url: str) -> RedisStore:
    """
    Creates a RedisStore and wraps it in a KV docstore. Mirrors your
    original: redis_byte_store = RedisStore(...); parent_document_store = create_kv_docstore(...)
    """
    store = RedisStore(redis_url=redis_url)
    return store


@task(
    name="setup-qdrant-client",
    retries=3,
    retry_delay_seconds=10,
    cache_key_fn=None  # NO_CACHE
)
def setup_qdrant_store_task(
    collection_names: list[str],
    vector_size: int,
    distance_metric: str,
    qdrant_url: str,
    api_key: str
) -> QdrantClient:
    """
    Initialize a Qdrant client and ensure each named collection exists with the given schema.
    Mirrors your original qdrant_client & create_collection(...) logic.
    """
    client = QdrantClient(url=qdrant_url, api_key=api_key, prefer_grpc=True)
    # For each collection, create if missing (with given vector_size & distance_metric)
    for coll in collection_names:
        if not client.collection_exists(coll):
            client.create_collection(
                collection_name=coll,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance[distance_metric.upper()]  # e.g. "COSINE"
                )
            )
    return client


@task(name="create-embeddings", retries=2, retry_delay_seconds=5, cache_key_fn=None)
def create_embeddings_task(model_name: str) -> OpenAIEmbeddings:
    """
    Initialize an OpenAIEmbeddings client.
    Mirrors your original: embeddings = OpenAIEmbeddings(model="text-embedding-3-small").
    """
    return OpenAIEmbeddings(model=model_name)


# ----------------------------------------
# 4. "Check existing data" & "validate ingestion" tasks
# ----------------------------------------

@task(name="check-existing-data", cache_policy=NO_CACHE)
def check_existing_data_task(
    redis_store: RedisStore,
    qdrant_client: QdrantClient,
    config: dict
) -> dict:
    """
    Count how many docs exist in Redis + each Qdrant collection.
    Mirrors your original check_existing_data logic.
    """
    logger = get_run_logger()
    redis_count = len(list(redis_store.yield_keys()))
    baseline_count = qdrant_client.count(collection_name=config["baseline_collection"]).count
    parent_child_count = qdrant_client.count(collection_name=config["parent_child_collection"]).count
    semantic_count = qdrant_client.count(collection_name=config["semantic_collection"]).count

    # If you want "complete" coverage, you might compare counts to len(documents) later.
    has_data = (redis_count > 0 and baseline_count > 0 and parent_child_count > 0 and semantic_count > 0)
    result = {
        "redis_count": redis_count,
        "baseline_count": baseline_count,
        "parent_child_count": parent_child_count,
        "semantic_count": semantic_count,
        "has_data": has_data
    }
    logger.info(f"Existing data status: {result}")
    return result


@task(name="validate-ingestion", retries=1, retry_delay_seconds=5, cache_policy=NO_CACHE)
def validate_ingestion_task(
    redis_store: RedisStore,
    qdrant_client: QdrantClient,
    config: dict,
    expected_min_docs: int
) -> bool:
    """
    Re-check counts after ingestion to ensure they meet or exceed expected_min_docs.
    Mirrors your original validate_ingestion logic.
    """
    logger = get_run_logger()
    redis_count = len(list(redis_store.yield_keys()))
    baseline_count = qdrant_client.count(collection_name=config["baseline_collection"]).count
    parent_child_count = qdrant_client.count(collection_name=config["parent_child_collection"]).count
    semantic_count = qdrant_client.count(collection_name=config["semantic_collection"]).count

    if (
        redis_count < expected_min_docs
        or baseline_count < expected_min_docs
        or parent_child_count < expected_min_docs
        or semantic_count < expected_min_docs
    ):
        raise ValueError(
            f"Ingestion validation failed: redis={redis_count}, "
            f"baseline={baseline_count}, parent_child={parent_child_count}, semantic={semantic_count}, "
            f"expected>= {expected_min_docs}"
        )
    logger.info("All ingestion counts ≥ expected_min_docs. Validation succeeded.")
    return True


# ----------------------------------------
# 5. Subflows for each ingestion variant
# ----------------------------------------

@flow(
    name="baseline-ingest-flow",
    retries=1,
    retry_delay_seconds=10
)
async def baseline_ingest_flow(
    documents: list,
    embeddings: OpenAIEmbeddings,
    config: dict
) -> dict:
    """
    Equivalent to your original "Level 1: Simple Vector Storage (Baseline)" block:
      baseline_vectorstore = QdrantVectorStore.from_documents(...)
    """
    logger = get_run_logger()
    collection_name = config["baseline_collection"]

    # Use from_documents(...) to embed + upsert in one step
    # This will churn through all docs, embed each chunk, and bulk‐upsert to Qdrant.
    baseline_vs = QdrantVectorStore.from_documents(
        documents,
        embeddings,
        url=config["qdrant_url"],
        api_key=config["qdrant_api_key"],
        prefer_grpc=True,
        collection_name=collection_name
    )

    # Count how many vectors were written
    count = baseline_vs.client.count(collection_name=collection_name)
    logger.info(f"[Baseline] Upserted {count} vectors into '{collection_name}'")
    return {"baseline_count": count}


@flow(
    name="parent-child-ingest-flow",
    retries=1,
    retry_delay_seconds=10
)
async def parent_child_ingest_flow(
    documents: list,
    redis_store: RedisStore,
    qdrant_client: QdrantClient,
    embeddings: OpenAIEmbeddings,
    config: dict
) -> dict:
    """
    Equivalent to your original "Level 2: Hierarchical Storage (Parent-Child)" block,
    including Redis KV store + Qdrant + ParentDocumentRetriever.add_documents(...)
    """
    logger = get_run_logger()
    parent_child_collection = config["parent_child_collection"]

    # 1. Set up the Qdrant vector store for child records
    parent_children_vs = QdrantVectorStore(
        embedding=embeddings,
        client=qdrant_client,
        collection_name=parent_child_collection
    )

    # 2. Build a ParentDocumentRetriever
    parent_docstore = create_kv_docstore(redis_store)
    child_splitter = RecursiveCharacterTextSplitter(chunk_size=config["chunk_size"])
    parent_retriever = ParentDocumentRetriever(
        vectorstore=parent_children_vs,
        docstore=parent_docstore,
        child_splitter=child_splitter,
    )

    # 3. Add all documents (this writes parent docs to Redis + child chunks to Qdrant)
    parent_retriever.add_documents(documents)

    # After add_documents, Redis KV store has parent pointers; Qdrant has child chunks
    # Count how many parents and children
    parent_count = len(list(redis_store.yield_keys()))
    child_count = qdrant_client.count(collection_name=parent_child_collection).count
    logger.info(f"[Parent-Child] Parent count={parent_count}, Child count={child_count}")
    return {"parent_count": parent_count, "child_count": child_count}


@flow(
    name="semantic-ingest-flow",
    retries=1,
    retry_delay_seconds=10
)
async def semantic_ingest_flow(
    semantic_documents: list,
    embeddings: OpenAIEmbeddings,
    config: dict
) -> dict:
    """
    Equivalent to your original "Level 3: Vector Storage by Semantic Chunks" block:
      semantic_chunker.split_documents(...) + QdrantVectorStore.from_documents(...)
    """
    logger = get_run_logger()
    semantic_collection = config["semantic_collection"]

    # 1. Upsert each semantic chunk into Qdrant
    semantic_vs = QdrantVectorStore.from_documents(
        semantic_documents,
        embeddings,
        url=config["qdrant_url"],
        api_key=config["qdrant_api_key"],
        prefer_grpc=True,
        collection_name=semantic_collection
    )

    count = semantic_vs.client.count(collection_name=semantic_collection)
    logger.info(f"[Semantic] Upserted {count} semantic chunks into '{semantic_collection}'")
    return {"semantic_count": count}


# ----------------------------------------
# 6. Master flow orchestration
# ----------------------------------------

@flow(
    name="master-ingestion-flow",
    task_runner=ThreadPoolTaskRunner(max_workers=4),
    retries=1,
    retry_delay_seconds=30,
    log_prints=True
)
async def master_ingestion_flow(
    data_dir: str,
    redis_url: str,
    config: dict,
    force_refresh: bool = False
) -> dict:
    logger = get_run_logger()
    logger.info("────────────────────────────────────────")
    logger.info("🚀 Starting master ingestion flow")
    logger.info(f"Config: {config}")

    # ─── Phase 1: Spin up Redis, Qdrant, and Embeddings in parallel ───
    # Use .submit() to get PrefectFutures, which are awaitable and allow
    # the ThreadPoolTaskRunner to execute them concurrently.
    redis_pfuture  = setup_redis_store_task.submit(redis_url)
    qdrant_pfuture = setup_qdrant_store_task.submit(
        [config["baseline_collection"], config["parent_child_collection"], config["semantic_collection"]],
        config["vector_size"],
        config["distance_metric"],
        config["qdrant_url"],
        config["qdrant_api_key"],
    )
    embed_pfuture  = create_embeddings_task.submit(config["embedding_model"])

    # To get results from sync tasks (running in ThreadPoolTaskRunner) in an async flow:
    # 1. Tasks are submitted via .submit(), returning PrefectConcurrentFuture.
    # 2. PrefectConcurrentFuture.result() is a blocking call.
    # 3. Wrap the blocking future.result() calls in asyncio.to_thread()
    #    to make them awaitable without blocking the main event loop.
    # 4. Use asyncio.gather to await these concurrently.

    logger.info("Submitting blocking tasks to asyncio.to_thread for result retrieval...")
    redis_result_task = asyncio.to_thread(redis_pfuture.result, raise_on_failure=True)
    qdrant_result_task = asyncio.to_thread(qdrant_pfuture.result, raise_on_failure=True)
    embed_result_task = asyncio.to_thread(embed_pfuture.result, raise_on_failure=True)

    logger.info("Gathering results from submitted tasks...")
    results = await asyncio.gather(
        redis_result_task,
        qdrant_result_task,
        embed_result_task,
    )
    redis_store, qdrant_client, embeddings = results[0], results[1], results[2]

    logger.info(f"Redis setup complete. Type of redis_store: {type(redis_store)}")
    logger.info(f"Qdrant setup complete. Type of qdrant_client: {type(qdrant_client)}")
    logger.info(f"Embeddings creation complete. Type of embeddings: {type(embeddings)}")

    # ─── Phase 2: Check existing data counts ───
    check_data_pfuture = check_existing_data_task.submit(redis_store, qdrant_client, config)
    data_status = await asyncio.to_thread(check_data_pfuture.result, raise_on_failure=True)

    if data_status["has_data"] and not force_refresh:
        logger.info("⚠️  Data already exists; skipping ingestion.")
        validate_skip_pfuture = validate_ingestion_task.submit(redis_store, qdrant_client, config, expected_min_docs=1)
        await asyncio.to_thread(validate_skip_pfuture.result, raise_on_failure=True)
        return {"status": "skipped_existing_data", **data_status}

    # ─── Phase 3: Load documents & create semantic chunks ───
    load_docs_pfuture = load_documents_task.submit(data_dir)
    all_docs = await asyncio.to_thread(load_docs_pfuture.result, raise_on_failure=True)

    create_chunks_pfuture = create_semantic_chunks_task.submit(all_docs)
    semantic_docs = await asyncio.to_thread(create_chunks_pfuture.result, raise_on_failure=True)

    expected_min_docs = len(all_docs)

    # ─── Phase 4: Run the three ingestion subflows in parallel ───
    # Note: baseline_ingest_flow, parent_child_ingest_flow, semantic_ingest_flow are @flow's,
    # so calling them directly returns an awaitable.

    baseline_coro      = baseline_ingest_flow(all_docs, embeddings, config)
    parent_child_coro = parent_child_ingest_flow(all_docs, redis_store, qdrant_client, embeddings, config)
    semantic_coro     = semantic_ingest_flow(semantic_docs, embeddings, config)

    baseline_res, parent_child_res, semantic_res = await asyncio.gather(
        baseline_coro,
        parent_child_coro,
        semantic_coro,
    )

    # ─── Phase 5: Post-ingestion validation ───
    validate_main_pfuture = validate_ingestion_task.submit(redis_store, qdrant_client, config, expected_min_docs)
    _ = await asyncio.to_thread(validate_main_pfuture.result, raise_on_failure=True)

    # ─── Phase 6: Create a Markdown summary artifact ───
    now = datetime.now().isoformat()
    summary_md = f"""
# Ingestion Summary – {now}

| Variant         | Collection                | Docs Ingested | Chunks/Children | Final Vectors | Embedding Model           | Chunk Size |
|----------------|---------------------------|---------------|-----------------|---------------|---------------------------|------------|
| Baseline       | {config['baseline_collection']}       | {baseline_res.get('baseline_count', 0)} | N/A             | {baseline_res.get('baseline_count', 0)} | {config['embedding_model']} | N/A        |
| Parent-Child   | {config['parent_child_collection']}   | {parent_child_res.get('parent_count', 0)} | {parent_child_res.get('child_count', 0)} | {parent_child_res.get('child_count', 0)} | {config['embedding_model']} | {config['chunk_size']} |
| Semantic       | {config['semantic_collection']}       | {len(semantic_docs) if 'semantic_docs' in locals() else 'N/A'} | N/A             | {semantic_res.get('semantic_count', 0)} | {config['embedding_model']} | N/A        |

## 1. Baseline Ingestion
- **Collection**: {config['baseline_collection']}
- **Documents ingested**: {baseline_res.get('baseline_count', 0)}
- **Embedding model**: {config['embedding_model']}

## 2. Parent-Child Ingestion
- **Collection**: {config['parent_child_collection']}
- **Documents ingested**: {parent_child_res.get('parent_count', 0)}
- **Chunks/Children created**: {parent_child_res.get('child_count', 0)}
- **Embedding model**: {config['embedding_model']}
- **Chunk size**: {config['chunk_size']}

## 3. Semantic Ingestion
- **Collection**: {config['semantic_collection']}
- **Semantic Chunks**: {semantic_res.get('semantic_count', 0)}
- **Embedding model**: {config['embedding_model']}

## Full Configuration
```json
{json.dumps(config, indent=2)}
```
"""
    await prefect.artifacts.create_markdown_artifact(
        key="ingestion-summary",
        markdown=summary_md
    )

    logger.info("✅ Master ingestion flow completed successfully.")
    return {
        "baseline": baseline_res,
        "parent_child": parent_child_res,
        "semantic": semantic_res,
        "validation": True,
    }

# ----------------------------------------
# 7. Entrypoint: run the master flow if this file is invoked directly
# ----------------------------------------
if __name__ == "__main__":
    # Define your configuration dictionary
    CONFIG = {
        "baseline_collection": "johnwick_baseline",
        "parent_child_collection": "johnwick_parent_children",
        "semantic_collection": "johnwick_semantic",
        "vector_size": 1536,
        "distance_metric": "COSINE",
        "chunk_size": 200,  # for RecursiveCharacterTextSplitter
        "qdrant_url": QDRANT_API_URL,
        "qdrant_api_key": QDRANT_API_KEY,
        "embedding_model": "text-embedding-3-small",
    }

    # Launch the flow (async context)
    asyncio.run(master_ingestion_flow(
        data_dir=str(DATA_DIR),
        redis_url="redis://localhost:6379",
        config=CONFIG,
        force_refresh=False
    ))
