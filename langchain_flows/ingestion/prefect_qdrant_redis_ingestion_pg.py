#!/usr/bin/env python3
"""
Modern Prefect-based ingestion pipeline for RAG data stores (Development Version).
Uses Prefect 3.4+ best practices with subflows for experimental precision.
"""

import os
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
import collections.abc

from prefect import flow, task, get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.blocks.system import Secret
from prefect.artifacts import create_markdown_artifact
from prefect.cache_policies import NO_CACHE, INPUTS
from prefect.futures import wait
from dotenv import load_dotenv
from prefect.variables import Variable

from langchain_core.documents import Document
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain.retrievers import ParentDocumentRetriever
from langchain_community.storage import RedisStore
from langchain.storage import create_kv_docstore
from qdrant_client import QdrantClient, models
from langchain_community.document_loaders.sql_database import SQLDatabaseLoader
from langchain_community.utilities.sql_database import SQLDatabase

from prefect.variables import Variable
# Variable.set("max_docs_debug", 5)

# Load environment variables
load_dotenv()

# os.environ["POSTGRES_HOST"],
# os.environ["POSTGRES_PORT"],
# os.environ["POSTGRES_USER"],
# os.environ["POSTGRES_PASSWORD"],
# os.environ["POSTGRES_DB"]
# os.environ["POSTGRES_TABLE"] # TABLE THAT CONTAINS LangChain Documents

# Configuration dataclass for type safety and environment loading
@dataclass
class PipelineConfig:
    baseline_collection: str
    parent_child_collection: str
    semantic_collection: str
    chunk_size: int = 200
    vector_size: int = 1536
    distance_metric: str = "COSINE"
    embedding_model: str = "text-embedding-3-small"
    redis_url: str = "redis://localhost:6379"
    redis_api_key: Optional[str] = None
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    data_dir: str = "data"

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        import os
        return cls(
            baseline_collection=os.getenv("BASELINE_COLLECTION", "azurearch_baseline"),
            parent_child_collection=os.getenv("PARENT_CHILD_COLLECTION", "azurearch_parent_children"),
            semantic_collection=os.getenv("SEMANTIC_COLLECTION", "azurearch_semantic"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "200")),
            vector_size=int(os.getenv("VECTOR_SIZE", "1536")),
            distance_metric=os.getenv("DISTANCE_METRIC", "COSINE"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            redis_api_key=os.getenv("REDIS_API_KEY"),
            qdrant_url=os.getenv("QDRANT_API_URL", "http://localhost:6333"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY"),
            data_dir=os.getenv("DATA_DIR", "data"),
        )

# ===== INFRASTRUCTURE TASKS (Shared) =====

@task(
    name="setup-redis-store",
    description="Initialize Redis store for parent documents",
    retries=3,
    retry_delay_seconds=5,
    tags=["infrastructure", "redis"],
    retry_condition_fn=lambda task, state, context: "ConnectionError" in str(state.message) or "connection" in str(state.message).lower(),
)
async def setup_redis_store(redis_url: str) -> RedisStore:
    """Setup Redis store with connection validation."""
    logger = get_run_logger()
    
    try:
        logger.info(f"🔄 Connecting to Redis at {redis_url}")
        redis_store = RedisStore(redis_url=redis_url)
        
        # Test connection by attempting to list keys
        try:
            list(redis_store.yield_keys())
            logger.info("✅ Redis connection established successfully")
            return redis_store
        except Exception as e:
            logger.error(f"❌ Redis connection test failed: {e}")
            raise
            
    except Exception as e:
        logger.error(f"❌ Failed to setup Redis store: {e}")
        raise

@task(
    name="setup-qdrant-store", 
    description="Initialize Qdrant vector store",
    retries=3,
    retry_delay_seconds=5,
    tags=["infrastructure", "qdrant"],
    retry_condition_fn=lambda task, state, context: "ConnectionError" in str(state.message) or "connection" in str(state.message).lower(),
)
async def setup_qdrant_store(
    collection_names: List[str], 
    vector_size: int = 1536,
    distance_metric: str = "COSINE"
) -> QdrantClient:
    """Setup Qdrant client and create collections if needed."""
    logger = get_run_logger()
    
    try:
        logger.info("🔄 Initializing Qdrant client")
        client = QdrantClient(
            url=os.getenv("QDRANT_API_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
            prefer_grpc=True
        )
        
        # Test connection
        collections = client.get_collections()
        logger.info(f"✅ Qdrant connection established. Found {len(collections.collections)} collections")
        
        # Create collections if they don't exist
        for collection_name in collection_names:
            if not client.collection_exists(collection_name):
                logger.info(f"🔄 Creating collection: {collection_name}")
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=getattr(models.Distance, distance_metric)
                    ),
                )
                logger.info(f"✅ Collection '{collection_name}' created successfully")
            else:
                logger.info(f"✅ Collection '{collection_name}' already exists")
            
        return client
        
    except Exception as e:
        logger.error(f"❌ Failed to setup Qdrant store: {e}")
        raise

@task(
    name="create-embeddings",
    description="Initialize embeddings model",
    tags=["embeddings", "model"],
    persist_result=False,
    cache_policy=INPUTS,
    cache_expiration=timedelta(hours=24),
)
async def create_embeddings(model_name: str) -> OpenAIEmbeddings:
    """Create embeddings model instance."""
    logger = get_run_logger()
    
    try:
        logger.info(f"🔄 Initializing embeddings model: {model_name}")
        embeddings = OpenAIEmbeddings(model=model_name)
        logger.info("✅ Embeddings model initialized")
        return embeddings
    except Exception as e:
        logger.error(f"❌ Failed to create embeddings: {e}")
        raise

def validate_and_flatten_metadata(docs, logger=None):
    """
    Ensure all Document.metadata fields are dicts, JSON-serializable, and flat.
    Flattens nested dicts (dot notation), removes non-serializable fields, and logs issues.
    """
    def flatten(d, parent_key='', sep='.'):  # flatten nested dicts
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                # Convert lists to JSON strings
                items.append((new_key, json.dumps(v)))
            else:
                items.append((new_key, v))
        return dict(items)

    for i, doc in enumerate(docs):
        # Parse string metadata
        if isinstance(doc.metadata, str):
            try:
                doc.metadata = json.loads(doc.metadata)
            except Exception as e:
                if logger:
                    logger.warning(f"Could not parse metadata for doc {i}: {e}")
                doc.metadata = {}
        # Ensure dict
        if not isinstance(doc.metadata, dict):
            if logger:
                logger.warning(f"Metadata for doc {i} is not a dict. Overwriting with empty dict.")
            doc.metadata = {}
        # Flatten
        doc.metadata = flatten(doc.metadata)
        # Remove non-serializable fields
        for k in list(doc.metadata.keys()):
            try:
                json.dumps(doc.metadata[k])
            except Exception:
                if logger:
                    logger.warning(f"Non-serializable metadata field '{k}' in doc {i}. Removing.")
                del doc.metadata[k]
    return docs

@task(
    name="load-documents-from-postgres",
    description="Load LangChain documents from Postgres table",
    retries=2,
    tags=["data-loading", "documents"],
    cache_policy=INPUTS,
    cache_expiration=timedelta(hours=24),
)
async def load_documents(data_dir: str) -> List[Document]:
    """Load documents from a Postgres table using direct JSONB extraction (identical to pg_to_qdrant_flow.py)."""
    logger = get_run_logger()
    try:
        pg_user = os.environ["POSTGRES_USER"]
        pg_password = os.environ["POSTGRES_PASSWORD"]
        pg_host = os.environ["POSTGRES_HOST"]
        pg_port = os.environ["POSTGRES_PORT"]
        pg_db = os.environ["POSTGRES_DB"]
        pg_table = os.environ["POSTGRES_TABLE"]
        conn_str = f"postgresql+psycopg2://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
        logger.info(f"Loading documents from Postgres table '{pg_table}' at {pg_host}:{pg_port}/{pg_db}, column 'document'")

        # Use SQLDatabaseLoader to fetch the entire JSONB column as a string
        query = f"SELECT document FROM {pg_table};"
        db = SQLDatabase.from_uri(conn_str)
        loader = SQLDatabaseLoader(query=query, db=db)
        loaded_rows = loader.load()
        logger.info(f"Loaded {len(loaded_rows)} rows from SQLDatabaseLoader.")

        processed_docs = []
        for i, doc in enumerate(loaded_rows):
            # Log only metadata for the first few rows
            if i < 5:
                logger.info(f"Row {i} extracted metadata type: {type(doc.metadata)}, value: {repr(doc.metadata)}")
            doc_data = doc.page_content
            # Try to parse until you get a dict (max 2 times)
            for _ in range(2):
                if isinstance(doc_data, str):
                    try:
                        doc_data = json.loads(doc_data)
                        if i < 5:
                            logger.info(f"Row {i} after JSON parse: type={type(doc_data)}, keys={list(doc_data.keys()) if isinstance(doc_data, dict) else 'N/A'}")
                    except Exception as e:
                        logger.warning(f"Row {i}: Could not parse JSON string: {e}. Skipping.")
                        doc_data = None
                        break
                else:
                    break
            # If dict with a single key (e.g., 'document'), extract that value
            if isinstance(doc_data, dict) and len(doc_data) == 1 and 'document' in doc_data:
                doc_data = doc_data['document']
                if i < 5:
                    logger.info(f"Row {i} unwrapped 'document' key: type={type(doc_data)}, keys={list(doc_data.keys()) if isinstance(doc_data, dict) else 'N/A'}")
            doc_obj = doc_data
            if not isinstance(doc_obj, dict):
                logger.warning(f"Row {i}: Could not get document dict after parsing. Skipping.")
                continue
            if i < 5:
                logger.info(f"Row {i} final doc_obj: type={type(doc_obj)}, keys={list(doc_obj.keys())}")
            # --- handle payload-wrapped format ---
            if "payload" in doc_obj and isinstance(doc_obj["payload"], dict):
                page_content = doc_obj["payload"].get("page_content")
                metadata = doc_obj["payload"].get("metadata", {})
            else:
                page_content = doc_obj.get("page_content")
                metadata = doc_obj.get("metadata", {})
            if not isinstance(page_content, str):
                logger.warning(f"Row {i}: 'page_content' is not a string or missing. Skipping.")
                continue
            if not isinstance(metadata, dict):
                logger.warning(f"Row {i}: 'metadata' is not a dict. Using empty dict.")
                metadata = {}
            if i < 5:
                logger.info(f"Row {i} extracted metadata type: {type(metadata)}, value: {repr(metadata)}")
            processed_docs.append(Document(page_content=page_content, metadata=metadata))

        # Use the same flattening and error handling as in pg_to_qdrant_flow.py
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
        for i, doc in enumerate(processed_docs):
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
    except Exception as e:
        logger.error(f"❌ Failed to load documents from Postgres: {e}")
        raise

@task(
    name="create-semantic-chunks",
    description="Create semantic chunks from documents",
    retries=2,
    retry_delay_seconds=30,  # longer delay for embedding service rate limits
    tags=["data-processing", "semantic"]
)
async def create_semantic_chunks(
    documents: List,
    embeddings: OpenAIEmbeddings
) -> List:
    """Create semantic chunks using SemanticChunker."""
    logger = get_run_logger()
    
    try:
        logger.info(f"🔄 Creating semantic chunks from {len(documents)} documents")
        
        semantic_chunker = SemanticChunker(
            embeddings,
            breakpoint_threshold_type="percentile"
        )
        
        semantic_documents = semantic_chunker.split_documents(documents)
        
        logger.info(f"✅ Created {len(semantic_documents)} semantic chunks")
        return semantic_documents
        
    except Exception as e:
        logger.error(f"❌ Failed to create semantic chunks: {e}")
        raise

# ===== SUBFLOW 1: BASELINE INGESTION =====

@flow(
    name="baseline-ingest-subflow",
    description="Ingest documents into baseline vector store",
    retries=1,
    retry_delay_seconds=20
)
async def baseline_ingest_flow(
    documents: List[Document],
    embeddings: OpenAIEmbeddings,
    collection_name: str,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Subflow for baseline vector store ingestion."""
    logger = get_run_logger()
    
    try:
        logger.info(f"🎯 BASELINE INGESTION START - Version: {experiment_version}")
        logger.info(f"📊 Processing {len(documents)} documents for collection: {collection_name}")
        
        if documents: # Add logging for the first document
            logger.info(f"[BASELINE_SUBFLOW_ENTRY] Doc 0 metadata: {repr(documents[0].metadata)}")
        else:
            logger.warning("[BASELINE_SUBFLOW_ENTRY] Received empty list of documents.")
            # Potentially return early or raise error if empty documents list is not expected
            return {{
                "subflow": "baseline",
                "collection_name": collection_name,
                "documents_ingested": 0,
                "final_count": 0,
                "error": "No documents provided to subflow",
                "experiment_version": experiment_version,
                "timestamp": datetime.now().isoformat()
            }}
            
        # Log metadata of first 3 documents
        for i, doc in enumerate(documents[:3]):
            logger.info(f"Document {i} metadata before ingestion: {doc.metadata}")
        # Use URL/API key directly to avoid client serialization issues
        baseline_vectorstore = QdrantVectorStore.from_documents(
            documents,
            embeddings,
            url=os.getenv("QDRANT_API_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
            prefer_grpc=True,
            collection_name=collection_name,
            content_payload_key="page_content",
            metadata_payload_key="metadata"
        )
        
        # Create client to check final count
        client = QdrantClient(
            url=os.getenv("QDRANT_API_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
            prefer_grpc=True
        )
        final_count = client.count(collection_name=collection_name).count
        
        result = {
            "subflow": "baseline",
            "collection_name": collection_name,
            "documents_ingested": len(documents),
            "final_count": final_count,
            "experiment_version": experiment_version,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"✅ BASELINE INGESTION COMPLETE: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Baseline ingestion failed: {e}")
        raise

# ===== SUBFLOW 2: PARENT-CHILD INGESTION =====

@flow(
    name="parent-child-ingest-subflow",
    description="Ingest documents into parent-child architecture",
    retries=1,
    retry_delay_seconds=20
)
async def parent_child_ingest_flow(
    documents: List,
    redis_store: RedisStore,
    qdrant_client: QdrantClient,
    embeddings: OpenAIEmbeddings,
    collection_name: str,
    chunk_size: int = 200,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Subflow for parent-child architecture ingestion."""
    logger = get_run_logger()
    
    try:
        logger.info(f"🎯 PARENT-CHILD INGESTION START - Version: {experiment_version}")
        logger.info(f"📊 Processing {len(documents)} documents with chunk_size: {chunk_size}")
        
        # Create docstore
        parent_document_store = create_kv_docstore(redis_store)
        
        # Create vectorstore
        vectorstore = QdrantVectorStore(
            embedding=embeddings,
            client=qdrant_client,
            collection_name=collection_name,
            content_payload_key="page_content",
            metadata_payload_key="metadata"
        )
        
        # Setup retriever
        child_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size)
        retriever = ParentDocumentRetriever(
            vectorstore=vectorstore,
            docstore=parent_document_store,
            child_splitter=child_splitter,
        )
        # Log metadata of first 3 documents
        for i, doc in enumerate(documents[:3]):
            logger.info(f"Document {i} metadata before parent-child ingestion: {doc.metadata}")
        
        # Flatten and validate metadata for all documents (including after any transformation)
        documents = validate_and_flatten_metadata(documents, logger=logger)
        
        # Perform ingestion
        start_time = datetime.now()
        retriever.add_documents(documents)
        ingestion_time = (datetime.now() - start_time).total_seconds()
        
        # Validate ingestion
        final_redis_count = len(list(parent_document_store.yield_keys()))
        final_qdrant_count = qdrant_client.count(collection_name=collection_name).count
        
        result = {
            "subflow": "parent-child",
            "collection_name": collection_name,
            "documents_ingested": len(documents),
            "redis_final_count": final_redis_count,
            "qdrant_final_count": final_qdrant_count,
            "chunk_size": chunk_size,
            "ingestion_time_seconds": ingestion_time,
            "experiment_version": experiment_version,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"✅ PARENT-CHILD INGESTION COMPLETE: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Parent-child ingestion failed: {e}")
        raise

# ===== SUBFLOW 3: SEMANTIC INGESTION =====

@flow(
    name="semantic-ingest-subflow", 
    description="Ingest semantic chunks into vector store",
    retries=1,
    retry_delay_seconds=20
)
async def semantic_ingest_flow(
    semantic_documents: List,
    embeddings: OpenAIEmbeddings,
    collection_name: str,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Subflow for semantic vector store ingestion."""
    logger = get_run_logger()
    
    try:
        logger.info(f"🎯 SEMANTIC INGESTION START - Version: {experiment_version}")
        logger.info(f"📊 Processing {len(semantic_documents)} semantic chunks")
        
        # Use URL/API key directly to avoid client serialization issues
        semantic_vectorstore = QdrantVectorStore.from_documents(
            semantic_documents,
            embeddings,
            url=os.getenv("QDRANT_API_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
            prefer_grpc=True,
            collection_name=collection_name,
            content_payload_key="page_content",
            metadata_payload_key="metadata"
        )
        
        # Create client to check final count
        client = QdrantClient(
            url=os.getenv("QDRANT_API_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
            prefer_grpc=True
        )
        final_count = client.count(collection_name=collection_name).count
        
        result = {
            "subflow": "semantic",
            "collection_name": collection_name,
            "chunks_ingested": len(semantic_documents),
            "final_count": final_count,
            "experiment_version": experiment_version,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"✅ SEMANTIC INGESTION COMPLETE: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Semantic ingestion failed: {e}")
        raise

# ===== VALIDATION TASKS =====

@task(
    name="check-existing-data",
    description="Check for existing data in Redis and Qdrant stores",
    retries=2,
    cache_policy=NO_CACHE,
    tags=["validation", "data-check"]
)
async def check_existing_data(
    redis_store: RedisStore, 
    qdrant_client: QdrantClient, 
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """Check if data already exists in all stores."""
    logger = get_run_logger()
    
    try:
        # Check Redis for parent documents
        redis_keys = list(redis_store.yield_keys())
        redis_count = len(redis_keys)
        
        # Check all Qdrant collections
        baseline_count = qdrant_client.count(collection_name=config["baseline_collection"]).count
        parent_child_count = qdrant_client.count(collection_name=config["parent_child_collection"]).count
        semantic_count = qdrant_client.count(collection_name=config["semantic_collection"]).count
        
        status = {
            "redis_count": redis_count,
            "baseline_count": baseline_count,
            "parent_child_count": parent_child_count,
            "semantic_count": semantic_count,
            "has_data": (redis_count > 0 and parent_child_count > 0 and 
                        baseline_count > 0 and semantic_count > 0)
        }
        
        logger.info(f"📊 Data Status: Redis={redis_count}, Baseline={baseline_count}, "
                   f"Parent-Child={parent_child_count}, Semantic={semantic_count}")
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Failed to check existing data: {e}")
        raise

@task(
    name="validate-ingestion",
    description="Validate that ingestion was successful",
    cache_policy=NO_CACHE,
    tags=["validation", "post-ingestion"]
)
async def validate_ingestion(
    redis_store: RedisStore,
    qdrant_client: QdrantClient,
    config: Dict[str, Any],
    expected_min_docs: int = 1
) -> Dict[str, Any]:
    """Validate ingestion results across all vector stores."""
    logger = get_run_logger()
    
    try:
        # Check final counts
        redis_count = len(list(redis_store.yield_keys()))
        baseline_count = qdrant_client.count(collection_name=config["baseline_collection"]).count
        parent_child_count = qdrant_client.count(collection_name=config["parent_child_collection"]).count  
        semantic_count = qdrant_client.count(collection_name=config["semantic_collection"]).count
        
        # Validation checks
        checks = {
            "redis_has_data": redis_count >= expected_min_docs,
            "baseline_has_data": baseline_count >= expected_min_docs,
            "parent_child_has_data": parent_child_count >= expected_min_docs,
            "semantic_has_data": semantic_count >= expected_min_docs,
            "data_consistency": all([redis_count > 0, baseline_count > 0, 
                                   parent_child_count > 0, semantic_count > 0])
        }
        
        all_passed = all(checks.values())
        
        validation_result = {
            "validation_passed": all_passed,
            "redis_count": redis_count,
            "baseline_count": baseline_count,
            "parent_child_count": parent_child_count,
            "semantic_count": semantic_count,
            "checks": checks,
            "timestamp": datetime.now().isoformat()
        }
        
        if all_passed:
            logger.info(f"✅ Validation passed: {validation_result}")
        else:
            logger.error(f"❌ Validation failed: {validation_result}")
            raise ValueError(f"Ingestion validation failed: {checks}")
            
        return validation_result
        
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")
        raise

# ===== MASTER ORCHESTRATION FLOW =====

@flow(
    name="rag-ingest-master",
    description="Master flow orchestrating three-tier RAG ingestion with subflows",
    task_runner=ThreadPoolTaskRunner(max_workers=4),
    log_prints=True,
    retries=1,
    retry_delay_seconds=30
)
async def master_ingestion_flow(
    config: Optional[PipelineConfig] = None,
    force_refresh: bool = False,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    logger = get_run_logger()
    # Use default config if none provided
    if config is None:
        config = PipelineConfig.from_env()
    logger.info(f"🚀 MASTER INGESTION FLOW START - Version: {experiment_version}")
    logger.info(f"📋 Config: {config}")
    try:
        # === PHASE 1: INFRASTRUCTURE SETUP ===
        logger.info("🔧 Phase 1: Infrastructure Setup")
        required_env_vars = ["QDRANT_API_URL", "OPENAI_API_KEY"]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")
        qdrant_url = config.qdrant_url
        qdrant_key = config.qdrant_api_key
        openai_key = os.getenv("OPENAI_API_KEY")
        logger.info(f"🔗 Qdrant URL: {qdrant_url}")
        logger.info(f"🔑 Qdrant API Key: {'Set' if qdrant_key else 'Not set (local mode)'}")
        logger.info(f"🤖 OpenAI API Key: {'Set' if openai_key else 'ERROR - This should not happen!'}")
        redis_future = setup_redis_store.submit(config.redis_url)
        collection_names = [
            config.baseline_collection,
            config.parent_child_collection, 
            config.semantic_collection
        ]
        qdrant_future = setup_qdrant_store.submit(
            collection_names, 
            config.vector_size, 
            config.distance_metric
        )
        embeddings_future = create_embeddings.submit(config.embedding_model)
        # Await infrastructure setup (proper async pattern)
        redis_store = await asyncio.to_thread(redis_future.result, raise_on_failure=True)
        qdrant_client = await asyncio.to_thread(qdrant_future.result, raise_on_failure=True)
        embeddings = await asyncio.to_thread(embeddings_future.result, raise_on_failure=True)

        # === PHASE 3: DATA LOADING (Moved before Phase 2) ===
        logger.info("📄 Phase 3: Data Loading")
        docs_future = load_documents.submit(config.data_dir)
        documents = await asyncio.to_thread(docs_future.result, raise_on_failure=True)
        # --- Debug limit: max_docs_debug ---
        max_docs = await Variable.get("max_docs_debug", default=None)
        if max_docs is not None:
            try:
                max_docs_int = int(max_docs)
                logger.info(f"⚠️  Limiting documents to first {max_docs_int} for debugging (max_docs_debug)")
                documents = documents[:max_docs_int]
            except Exception as e:
                logger.warning(f"Could not apply max_docs_debug: {e}")
        if not documents:
            raise ValueError("No documents loaded - check data directory and files")
        semantic_docs_future = create_semantic_chunks.submit(documents, embeddings)
        semantic_documents = await asyncio.to_thread(semantic_docs_future.result, raise_on_failure=True)
        # --- Debug limit: max_docs_debug for semantic chunks ---
        if max_docs is not None:
            try:
                max_docs_int = int(max_docs)
                logger.info(f"⚠️  Limiting semantic chunks to first {max_docs_int} for debugging (max_docs_debug)")
                semantic_documents = semantic_documents[:max_docs_int]
            except Exception as e:
                logger.warning(f"Could not apply max_docs_debug to semantic chunks: {e}")
        # === PHASE 2: DATA ASSESSMENT (Now after Data Loading) ===
        logger.info("📊 Phase 2: Data Assessment")
        data_status = await check_existing_data(redis_store, qdrant_client, config.__dict__)
        complete_ingestion = (
            data_status["baseline_count"] >= len(documents) and
            data_status["parent_child_count"] >= len(documents) and  
            data_status["semantic_count"] >= len(semantic_documents) and
            data_status["redis_count"] >= len(documents)
        )
        if complete_ingestion and not force_refresh:
            logger.info("⚠️  Complete data already exists. Use force_refresh=True to overwrite.")
            validation_result = await validate_ingestion(
                redis_store, qdrant_client, config.__dict__
            )
            return {
                "status": "skipped_existing_data",
                "data_status": data_status,
                "validation": validation_result,
                "experiment_version": experiment_version,
                "timestamp": datetime.now().isoformat()
            }
        # === PHASE 4: PARALLEL SUBFLOW INGESTION ===
        logger.info("🎯 Phase 4: Parallel Subflow Ingestion")
        baseline_coro = baseline_ingest_flow(
            documents, embeddings, config.baseline_collection, experiment_version
        )
        parent_child_coro = parent_child_ingest_flow(
            documents, redis_store, qdrant_client, embeddings, 
            config.parent_child_collection, config.chunk_size, experiment_version
        )
        semantic_coro = semantic_ingest_flow(
            semantic_documents, embeddings, config.semantic_collection, experiment_version
        )
        baseline_result, parent_child_result, semantic_result = await asyncio.gather(
            baseline_coro,
            parent_child_coro,
            semantic_coro
        )
        # === PHASE 5: VALIDATION ===
        logger.info("✅ Phase 5: Final Validation")
        validation_result = await validate_ingestion(
            redis_store, qdrant_client, config.__dict__, len(documents)
        )
        # === PHASE 6: REPORTING ===
        logger.info("📋 Phase 6: Reporting")
        summary = f"""# 🎯 Three-Tier RAG Ingestion Complete - {experiment_version}\n\n## 📊 Experiment Configuration\n- **Version**: {experiment_version}\n- **Baseline Collection**: {config.baseline_collection}\n- **Parent-Child Collection**: {config.parent_child_collection}\n- **Semantic Collection**: {config.semantic_collection}\n- **Chunk Size**: {config.chunk_size}\n- **Embedding Model**: {config.embedding_model}\n\n## 📈 Processing Summary  \n- **Documents Processed**: {len(documents)}\n- **Semantic Chunks Created**: {len(semantic_documents)}\n\n## 🎯 Subflow Results\n\n### Baseline Vector Store\n- **Collection**: {baseline_result['collection_name']}\n- **Documents**: {baseline_result['documents_ingested']}\n- **Final Vectors**: {baseline_result['final_count']}\n- **Version**: {baseline_result['experiment_version']}\n\n### Parent-Child Architecture  \n- **Collection**: {parent_child_result['collection_name']}\n- **Documents**: {parent_child_result['documents_ingested']}\n- **Redis Parents**: {parent_child_result['redis_final_count']}\n- **Child Vectors**: {parent_child_result['qdrant_final_count']}\n- **Ingestion Time**: {parent_child_result['ingestion_time_seconds']:.2f}s\n- **Chunk Size**: {parent_child_result['chunk_size']}\n- **Version**: {parent_child_result['experiment_version']}\n\n### Semantic Vector Store\n- **Collection**: {semantic_result['collection_name']} \n- **Chunks**: {semantic_result['chunks_ingested']}\n- **Final Vectors**: {semantic_result['final_count']}\n- **Version**: {semantic_result['experiment_version']}\n\n## ✅ Validation: {'PASSED' if validation_result['validation_passed'] else 'FAILED'}\n\n## 🕐 Completed: {datetime.now().isoformat()}\n\n---\n*Ready for retrieval method comparison in notebook!*\n"""
        safe_key_version = experiment_version.lower().replace('.', '-').replace(' ', '-').replace('_', '-')
        await create_markdown_artifact(
            key=f"three-tier-ingestion-{safe_key_version}",
            markdown=summary,
            description=f"Three-Tier RAG Ingestion Summary - {experiment_version}"
        )
        final_result = {
            "status": "completed",
            "experiment_version": experiment_version,
            "config": config.__dict__,
            "data_status": data_status,
            "subflow_results": {
                "baseline": baseline_result,
                "parent_child": parent_child_result,
                "semantic": semantic_result
            },
            "validation": validation_result,
            "summary_stats": {
                "documents_processed": len(documents),
                "semantic_chunks": len(semantic_documents),
                "total_vectors": (
                    baseline_result['final_count'] + 
                    parent_child_result['qdrant_final_count'] + 
                    semantic_result['final_count']
                )
            },
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"🎉 MASTER INGESTION FLOW COMPLETE: {experiment_version}")
        return final_result
    except Exception as e:
        logger.error(f"❌ Master ingestion flow failed: {e}")
        raise

# ===== CONVENIENCE FUNCTIONS FOR INDIVIDUAL SUBFLOW EXECUTION =====

async def run_baseline_only(
    config: Optional[PipelineConfig] = None,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Run only baseline ingestion subflow."""
    if config is None:
        config = PipelineConfig.from_env()
        
    embeddings = await create_embeddings(config.embedding_model)
    documents = await load_documents(config.data_dir)
    
    return await baseline_ingest_flow(
        documents, embeddings, config.baseline_collection, experiment_version
    )

async def run_semantic_only(
    config: Optional[PipelineConfig] = None,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Run only semantic ingestion subflow."""
    if config is None:
        config = PipelineConfig.from_env()
        
    embeddings = await create_embeddings(config.embedding_model)
    documents = await load_documents(config.data_dir)
    semantic_documents = await create_semantic_chunks(documents, embeddings)
    
    return await semantic_ingest_flow(
        semantic_documents, embeddings, config.semantic_collection, experiment_version
    )

async def run_parent_child_only(
    config: Optional[PipelineConfig] = None,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Run only parent-child ingestion subflow."""
    if config is None:
        config = PipelineConfig.from_env()
        
    redis_store = await setup_redis_store(config.redis_url)
    qdrant_client = await setup_qdrant_store(
        [config.parent_child_collection],
        config.vector_size, 
        config.distance_metric
    )
    embeddings = await create_embeddings(config.embedding_model)
    documents = await load_documents(config.data_dir)
    
    return await parent_child_ingest_flow(
        documents, redis_store, qdrant_client, embeddings,
        config.parent_child_collection, config.chunk_size, experiment_version
    )

if __name__ == "__main__":
    # Run the master flow (one command for everything)
    # asyncio.run(master_ingestion_flow()) 

    # To run only a specific subflow for debugging:
    # asyncio.run(run_parent_child_only())
    # asyncio.run(run_semantic_only())
    asyncio.run(run_baseline_only()) # Focus on baseline for now 