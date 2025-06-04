#!/usr/bin/env python3
"""
Prefect-based ingestion pipeline for RAG data stores.
Simplified version focusing on a robust baseline ingestion path,
with an option to limit processed documents via a Prefect Variable.
"""

import os
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
import collections.abc
import psycopg2

from prefect import flow, task, get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.variables import Variable # Added for MAX_DOCS_DEBUG
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
@dataclass
class PipelineConfig:
    baseline_collection: str = os.getenv("BASELINE_COLLECTION", "pg_jsonb_limited_docs") # New default for clarity
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    qdrant_url: str = os.getenv("QDRANT_API_URL", "http://localhost:6333")
    qdrant_api_key: Optional[str] = os.getenv("QDRANT_API_KEY")
    
    # PostgreSQL connection details
    pg_host: str = os.getenv("POSTGRES_HOST", "localhost")
    pg_port: str = os.getenv("POSTGRES_PORT", "5432")
    pg_user: str = os.environ.get("POSTGRES_USER")
    pg_password: str = os.environ.get("POSTGRES_PASSWORD")
    pg_db: str = os.environ.get("POSTGRES_DB")
    pg_table: str = os.getenv("POSTGRES_TABLE")
    jsonb_column_name: str = os.getenv("JSONB_COLUMN_NAME", "document")

    def __post_init__(self):
        if not all([self.pg_user, self.pg_password, self.pg_db, self.pg_table]):
            raise ValueError("Missing one or more PostgreSQL env vars: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_TABLE")
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("Missing OPENAI_API_KEY environment variable.")

# --- Synchronous Data Preparation Tasks ---

@task(
    name="create-embeddings-sync",
    description="Initializes OpenAIEmbeddings model.",
    tags=["embeddings", "sync"],
    retries=2,
    retry_delay_seconds=5,
)
def create_embeddings_sync(model_name: str) -> OpenAIEmbeddings:
    logger = get_run_logger()
    logger.info(f"Creating OpenAIEmbeddings model: {model_name}")
    try:
        embeddings = OpenAIEmbeddings(model=model_name)
        logger.info("OpenAIEmbeddings model created successfully.")
        return embeddings
    except Exception as e:
        logger.error(f"Failed to create OpenAIEmbeddings model: {e}")
        raise

@task(
    name="fetch-pg-documents-sync",
    description="Fetches and prepares LangChain Documents from PostgreSQL.",
    tags=["data-loading", "postgres", "sync"],
    retries=2,
    retry_delay_seconds=10,
)
def fetch_pg_documents_sync(config: PipelineConfig) -> List[Document]:
    logger = get_run_logger()
    logger.info(f"Connecting to PostgreSQL: {config.pg_host}:{config.pg_port}, DB: {config.pg_db}, Table: {config.pg_table}")

    conn_string = f"host='{config.pg_host}' port='{config.pg_port}' dbname='{config.pg_db}' user='{config.pg_user}' password='{config.pg_password}'"
    
    prepared_documents = []
    conn = None
    try:
        conn = psycopg2.connect(conn_string)
        with conn.cursor() as cur:
            query = f"SELECT document FROM {config.pg_table}"
            logger.info(f"Executing query: {query}")
            cur.execute(query)
            rows = cur.fetchall()
            logger.info(f"Fetched {len(rows)} rows from table '{config.pg_table}'.")

            for i, row_data in enumerate(rows):
                if not row_data or row_data[0] is None:
                    logger.warning(f"Row {i} is empty or document is NULL. Skipping.")
                    continue
                
                doc_data_from_db = row_data[0]

                if isinstance(doc_data_from_db, str):
                    try:
                        doc_obj = json.loads(doc_data_from_db)
                    except json.JSONDecodeError as e:
                        logger.error(f"Row {i}: Error parsing JSON string: {e}. Data: {doc_data_from_db[:200]}. Skipping.")
                        continue
                elif isinstance(doc_data_from_db, dict):
                    doc_obj = doc_data_from_db
                else:
                    logger.warning(f"Row {i}: document is of unexpected type {type(doc_data_from_db)}. Skipping.")
                    continue
                
                # --- NEW LOGIC: handle payload-wrapped format ---
                if "payload" in doc_obj and isinstance(doc_obj["payload"], dict):
                    page_content = doc_obj["payload"].get("page_content")
                    metadata = doc_obj["payload"].get("metadata", {})
                else:
                    page_content = doc_obj.get("page_content")
                    metadata = doc_obj.get("metadata", {})

                if not isinstance(page_content, str):
                    logger.warning(f"Row {i}: 'page_content' is not a string or is missing. Type: {type(page_content)}. Skipping.")
                    continue
                
                if not isinstance(metadata, dict):
                    logger.warning(f"Row {i}: 'metadata' is not a dict. Using empty. Type: {type(metadata)}.")
                    metadata = {}
                
                if i < 3: # Log only a few for brevity
                    logger.debug(f"Row {i} raw metadata before Document creation: {metadata}")

                prepared_documents.append(Document(page_content=page_content, metadata=metadata))
        
        logger.info(f"Successfully prepared {len(prepared_documents)} LangChain documents.")

    except psycopg2.Error as e:
        logger.error(f"PostgreSQL connection or query error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during document fetching/preparation: {e}")
        raise
    finally:
        if conn:
            conn.close()
            
    return prepared_documents

@task(
    name="validate-and-flatten-metadata-sync",
    description="Validates and flattens document metadata.",
    tags=["data-processing", "metadata", "sync"],
)
def validate_and_flatten_metadata_sync(docs: List[Document]) -> List[Document]:
    logger = get_run_logger()
    if not docs:
        logger.info("No documents to validate/flatten.")
        return []
    logger.info(f"Validating and flattening metadata for {len(docs)} documents.")

    def flatten_dict(d, parent_key='', sep='_'):
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, collections.abc.MutableMapping):
                items.extend(flatten_dict(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                processed_list = []
                for item_idx, item_val in enumerate(v):
                    if not isinstance(item_val, (str, int, float, bool)) and item_val is not None:
                        logger.debug(f"Metadata key '{new_key}', list item {item_idx} is complex type {type(item_val)}. Converting to string.")
                        processed_list.append(str(item_val))
                    else:
                        processed_list.append(item_val)
                items.append((new_key, processed_list))
            else:
                items.append((new_key, v))
        return dict(items)

    validated_docs = []
    for i, doc in enumerate(docs):
        if not isinstance(doc, Document):
            logger.warning(f"Item {i} is not a Document object. Skipping.")
            continue

        current_metadata = doc.metadata
        if not isinstance(current_metadata, dict):
            logger.warning(f"Doc {i} metadata is type {type(current_metadata)}, not dict. Resetting to empty. Original: {current_metadata}")
            current_metadata = {}
        
        try:
            flattened_meta = flatten_dict(current_metadata)
            final_meta = {}
            for k, v in flattened_meta.items():
                try:
                    json.dumps({k: v}) 
                    final_meta[k] = v
                except TypeError:
                    logger.warning(f"Doc {i}, metadata key '{k}', value '{v}' (type {type(v)}) not JSON serializable after flattening. Converting to string.")
                    final_meta[k] = str(v)
            
            doc.metadata = final_meta
            validated_docs.append(doc)
            if i < 3: 
                 logger.info(f"Doc {i} validated & flattened metadata: {doc.metadata}")
        except Exception as e:
            logger.error(f"Error processing metadata for doc {i}: {e}. Original metadata: {doc.metadata}")
            doc.metadata = {"_processing_error": str(e)} 
            validated_docs.append(doc)
            
    logger.info(f"Finished validating and flattening. {len(validated_docs)} documents processed.")
    return validated_docs

# --- Asynchronous Ingestion Subflow ---

@flow(
    name="baseline-ingest-subflow",
    description="Ingests documents into a baseline Qdrant collection.",
    task_runner=ThreadPoolTaskRunner()
)
async def baseline_ingest_subflow(
    documents: List[Document],
    embeddings: OpenAIEmbeddings,
    config: PipelineConfig,
    experiment_version: str = "v1.0"
):
    logger = get_run_logger()
    collection_name = config.baseline_collection
    
    if not documents:
        logger.warning(f"Baseline Ingest (v{experiment_version}): No documents for collection '{collection_name}'. Skipping.")
        return {"status": "skipped_empty_docs", "collection_name": collection_name, "ingested_count": 0}

    logger.info(f"Baseline Ingest (v{experiment_version}): Starting for {len(documents)} docs into '{collection_name}'.")
    if documents and documents[0].metadata: # Ensure documents list is not empty before accessing
        logger.info(f"Sample Doc 0 metadata PRE-INGESTION: {documents[0].metadata}")
    
    try:
        vector_store = QdrantVectorStore.from_documents(
            documents=documents,
            embedding=embeddings,
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=collection_name,
            prefer_grpc=False,
        )
        logger.info(f"Baseline Ingest (v{experiment_version}): Successfully ingested {len(documents)} docs into '{collection_name}'.")
        return {"status": "success", "collection_name": collection_name, "ingested_count": len(documents)}
    except Exception as e:
        logger.error(f"Baseline Ingest (v{experiment_version}): Error during Qdrant ingestion for '{collection_name}': {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise

# --- Main Orchestrating Flow ---

@flow(
    name="pg-to-qdrant-main-flow",
    description="Orchestrates ingestion from PostgreSQL to Qdrant.",
    task_runner=ThreadPoolTaskRunner()
)
async def pg_to_qdrant_main_flow(config: PipelineConfig):
    """
    Main Prefect flow to orchestrate the ingestion from PostgreSQL to Qdrant.
    """
    logger = get_run_logger()
    logger.info(f"Starting PostgreSQL to Qdrant ingestion flow with config: {config}")

    # 1. Create Embeddings Model (Synchronous Task)
    embeddings_future = create_embeddings_sync.submit(config.embedding_model)
    # Fetch all documents (no limit)
    raw_documents_future = fetch_pg_documents_sync.submit(config)
    
    logger.info("Waiting for embeddings creation and document fetching...")
    embeddings = embeddings_future.result(raise_on_failure=True)
    raw_documents = raw_documents_future.result(raise_on_failure=True)

    if not raw_documents:
        logger.error("No documents fetched from PostgreSQL. Halting flow.")
        return {"status": "no_docs_fetched", "ingested_count": 0, "experiment_version": "manual-run-pg-qdrant"}
    logger.info(f"Fetched {len(raw_documents)} raw documents.")

    validated_documents_future = validate_and_flatten_metadata_sync.submit(raw_documents)
    logger.info("Waiting for metadata validation and flattening...")
    validated_documents = validated_documents_future.result(raise_on_failure=True)

    if not validated_documents:
        logger.warning("No documents after validation/flattening. Ingestion may be empty or only contain error placeholders.")
    logger.info(f"{len(validated_documents)} documents after validation/flattening.")

    ingestion_result = await baseline_ingest_subflow(
        documents=validated_documents,
        embeddings=embeddings,
        config=config,
        experiment_version="manual-run-pg-qdrant"
    )

    logger.info(f"PostgreSQL to Qdrant Main Flow completed. Result: {ingestion_result}")
    return ingestion_result

if __name__ == "__main__":
    # To use the MAX_DOCS_DEBUG feature:
    # 1. Set the variable in your Prefect UI or via Prefect CLI:
    #    prefect variable set MAX_DOCS_DEBUG "5"
    # 2. Then run this script.
    # To remove the limit, delete the variable or set it to a non-integer/empty value.
    asyncio.run(pg_to_qdrant_main_flow(config=PipelineConfig()))
