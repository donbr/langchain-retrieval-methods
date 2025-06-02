from pathlib import Path
import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
import json
from typing import List
import hashlib

from prefect import flow, task, get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.cache_policies import NO_CACHE

from langchain_core.documents import Document
from langchain_community.storage import RedisStore
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient, models
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import create_kv_docstore
from langchain_community.document_loaders.csv_loader import CSVLoader

# ────────────────────────────────────────────────────────────────────────────────
# 1) CONFIG & CLIENT INITIALIZATION
# ────────────────────────────────────────────────────────────────────────────────

@task(name="Init Clients", retries=2, retry_delay_seconds=5)
def init_clients_task(
    redis_url: str,
    qdrant_url: str,
    qdrant_api_key: str,
    embedding_model: str,
):
    # Set up Redis, Qdrant, Embeddings once
    redis_store = RedisStore(redis_url=redis_url)
    q_client = QdrantClient(
        url=qdrant_url, api_key=qdrant_api_key, prefer_grpc=True
    )
    embeddings = OpenAIEmbeddings(model=embedding_model)
    return {
        "redis": redis_store,
        "qdrant": q_client,
        "embeddings": embeddings,
        "qdrant_url": qdrant_url,
        "qdrant_api_key": qdrant_api_key,
    }


# ────────────────────────────────────────────────────────────────────────────────
# 2) DETECT "WHAT'S NEW" (FILE-BASED EXAMPLE)
# ────────────────────────────────────────────────────────────────────────────────

@task(name="Scan for New Files", cache_policy=NO_CACHE)
def diff_files_task(
    data_dir: Path, redis_store: RedisStore
) -> List[Path]:
    """
    Compare file checksums in `data_dir` against Redis manifest.
    Return only files whose checksum has changed or are entirely new.
    """
    new_files = []
    for fp in data_dir.glob("*.csv"):
        content = fp.read_bytes()
        md5 = hashlib.md5(content).hexdigest()
        stored = redis_store.client.hget("file_manifest", fp.name)
        if stored is None or stored.decode() != md5:
            new_files.append(fp)
    return new_files


# ────────────────────────────────────────────────────────────────────────────────
# 3) LOAD & PREPARE "NEW" DOCUMENTS
# ────────────────────────────────────────────────────────────────────────────────

@task(name="Load New Docs", cache_policy=NO_CACHE)
def load_new_docs_task(
    new_files: List[Path]
) -> List[Document]:
    """
    Use CSVLoader on each new file; add a unique doc.metadata['id'] based on (filename,row_idx).
    """
    all_new_docs: List[Document] = []
    for fp in new_files:
        loader = CSVLoader(
            file_path=fp,
            metadata_columns=["Review_Date", "Review_Title", "Review_Url", "Author", "Rating"],
        )
        docs = loader.load()
        for i, doc in enumerate(docs):
            unique_id = f"{fp.name}#{i}"
            doc.metadata["id"] = unique_id
            all_new_docs.append(doc)
    return all_new_docs


# ────────────────────────────────────────────────────────────────────────────────
# 4) FILTER OUT DOCS ALREADY IN REDIS / QDRANT (ROW-LEVEL DELTA)
# ────────────────────────────────────────────────────────────────────────────────

@task(name="Filter Already Ingested Docs", cache_policy=NO_CACHE)
def filter_ingested_docs_task(
    docs: List[Document], redis_store: RedisStore
) -> List[Document]:
    """
    Remove any doc whose `id` is already tracked in Redis manifest.
    """
    filtered: List[Document] = []
    for doc in docs:
        if not redis_store.client.hexists("doc_manifest", doc.metadata["id"]):
            filtered.append(doc)
    return filtered


# ────────────────────────────────────────────────────────────────────────────────
# 5) UPDATE THE REDIS MANIFEST
# ────────────────────────────────────────────────────────────────────────────────

@task(name="Update Doc Manifest", cache_policy=NO_CACHE)
def update_doc_manifest_task(
    docs: List[Document], redis_store: RedisStore
) -> None:
    """
    After successfully computing embeddings (or after ingestion), write each doc.id→"ingested"
    into Redis so we don't ingest it next time.
    """
    pipe = redis_store.client.pipeline()
    for doc in docs:
        pipe.hset("doc_manifest", doc.metadata["id"], "1")
    pipe.execute()


# ────────────────────────────────────────────────────────────────────────────────
# 6) GENERIC "INGEST VARIANT" TASK THAT ONLY PROCESSES DELTA
# ────────────────────────────────────────────────────────────────────────────────

@task(name="Ingest Variant", retries=2, retry_delay_seconds=15, cache_policy=NO_CACHE)
def ingest_variant_task(
    mode: str,
    docs: List[Document],
    clients: dict,
    collections: dict,
    chunk_size: int = 200,
):
    """
    - mode ∈ {"baseline", "parent_child", "semantic"}  
    - `collections` is a dict mapping mode→collection_name  
    """
    q_client: QdrantClient = clients["qdrant"]
    embeddings = clients["embeddings"]
    redis_store: RedisStore = clients["redis"]
    qdrant_url = clients["qdrant_url"]
    qdrant_api_key = clients["qdrant_api_key"]

    if mode == "baseline":
        store = QdrantVectorStore.from_documents(
            docs,
            embeddings,
            url=qdrant_url,
            api_key=qdrant_api_key,
            prefer_grpc=True,
            collection_name=collections["baseline"],
        )
        return {"mode": mode, "vector_count": q_client.count(collection_name=collections["baseline"]).count}

    if mode == "parent_child":
        parent_doc_store = create_kv_docstore(redis_store)
        vectorstore = QdrantVectorStore(
            embedding=embeddings,
            client=q_client,
            collection_name=collections["parent_child"],
        )
        retriever = ParentDocumentRetriever(
            vectorstore=vectorstore,
            docstore=parent_doc_store,
            child_splitter=RecursiveCharacterTextSplitter(chunk_size=chunk_size),
        )
        retriever.add_documents(docs)
        return {"mode": mode, "vector_count": q_client.count(collection_name=collections["parent_child"]).count}

    if mode == "semantic":
        chunker = SemanticChunker(embeddings, breakpoint_threshold_type="percentile")
        sem_docs = chunker.split_documents(docs)
        store = QdrantVectorStore.from_documents(
            sem_docs,
            embeddings,
            url=qdrant_url,
            api_key=qdrant_api_key,
            prefer_grpc=True,
            collection_name=collections["semantic"],
        )
        return {"mode": mode, "vector_count": q_client.count(collection_name=collections["semantic"]).count}

    raise ValueError(f"Unknown mode {mode}")


# ────────────────────────────────────────────────────────────────────────────────
# 7) MASTER FLOW: TIES EVERYTHING TOGETHER
# ────────────────────────────────────────────────────────────────────────────────

@flow(name="Incremental Ingestion Flow", log_prints=True)
def incremental_ingest_flow():
    logger = get_run_logger()

    # Load config (could be a dataclass like PipelineConfig, omitted for brevity)
    data_dir = Path("data/")
    redis_url = "redis://localhost:6379"
    qdrant_url = "http://localhost:6333"
    qdrant_api_key = ""
    embedding_model = "text-embedding-3-small"
    collections = {
        "baseline": "johnwick_baseline",
        "parent_child": "johnwick_parent_children",
        "semantic": "johnwick_semantic",
    }
    force_refresh = False

    # 1) Init clients once
    clients = init_clients_task(
        redis_url=redis_url,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
        embedding_model=embedding_model,
    )

    # 2) Compute which files are new/updated
    new_files = diff_files_task(data_dir, clients["redis"])
    if not new_files:
        logger.info("No new/updated files. Exiting early.")
        return

    # 3) Load only the NEW/UPDATED docs
    new_docs = load_new_docs_task(new_files)

    # 4) Filter out any docs already ingested (in case a file changed partially)
    delta_docs = filter_ingested_docs_task(new_docs, clients["redis"])
    if not delta_docs:
        logger.info("All new files contain no net-new docs. Exiting early.")
        return

    # 5) Ingest the DELTA docs for each variant in parallel
    futures = []
    for mode in ["baseline", "parent_child", "semantic"]:
        futures.append(
            ingest_variant_task.submit(
                mode, delta_docs, clients, collections, 200
            )
        )
    results = [f.result() for f in futures]

    # 6) Update the Redis manifest so we don't re-ingest these doc IDs next time
    update_doc_manifest_task(delta_docs, clients["redis"])

    # 7) Summarize what happened
    for r in results:
        logger.info(f"→ {r['mode']}: {r['vector_count']} new vectors added.")

    return results


if __name__ == "__main__":
    incremental_ingest_flow()
