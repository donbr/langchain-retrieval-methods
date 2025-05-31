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

from prefect import flow, task, get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.blocks.system import Secret
from prefect.artifacts import create_markdown_artifact
from prefect.cache_policies import NO_CACHE
from prefect.futures import wait
from dotenv import load_dotenv

from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain.retrievers import ParentDocumentRetriever
from langchain_community.storage import RedisStore
from langchain.storage import create_kv_docstore
from qdrant_client import QdrantClient, models

# Load environment variables
load_dotenv()

# Configuration
DEFAULT_CONFIG = {
    "baseline_collection": "johnwick_baseline",
    "parent_child_collection": "johnwick_parent_children", 
    "semantic_collection": "johnwick_semantic",
    "chunk_size": 200,
    "embedding_model": "text-embedding-3-small",
    "redis_url": "redis://localhost:6379",
    "data_dir": "data",
    "vector_size": 1536,
    "distance_metric": "COSINE"
}

# ===== INFRASTRUCTURE TASKS (Shared) =====

@task(
    name="setup-redis-store",
    description="Initialize Redis store for parent documents",
    retries=3,
    retry_delay_seconds=5,
    tags=["infrastructure", "redis"]
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
    tags=["infrastructure", "qdrant"]
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
    persist_result=False
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

@task(
    name="load-documents",
    description="Load John Wick review documents from CSV files",
    retries=2,
    tags=["data-loading", "documents"]
)
async def load_documents(data_dir: str) -> List:
    """Load documents from CSV files with metadata enhancement."""
    logger = get_run_logger()
    
    try:
        data_path = Path(data_dir)
        if not data_path.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")
            
        all_review_docs = []
        
        for i in range(1, 5):
            file_path = data_path / f"john_wick_{i}.csv"
            if not file_path.exists():
                logger.warning(f"⚠️  File not found: {file_path}")
                continue
                
            logger.info(f"📄 Loading {file_path}")
            loader = CSVLoader(
                file_path=str(file_path),
                metadata_columns=["Review_Date", "Review_Title", "Review_Url", "Author", "Rating"]
            )
            
            movie_docs = loader.load()
            for doc in movie_docs:
                # Enhance metadata
                doc.metadata["Movie_Title"] = f"John Wick {i}"
                doc.metadata["Rating"] = int(doc.metadata["Rating"]) if doc.metadata["Rating"] else 0
                doc.metadata["last_accessed_at"] = datetime.now().isoformat()
                doc.metadata["ingestion_batch"] = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            all_review_docs.extend(movie_docs)
            logger.info(f"✅ Loaded {len(movie_docs)} documents from John Wick {i}")
        
        logger.info(f"✅ Total documents loaded: {len(all_review_docs)}")
        return all_review_docs
        
    except Exception as e:
        logger.error(f"❌ Failed to load documents: {e}")
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
    documents: List,
    embeddings: OpenAIEmbeddings,
    collection_name: str,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Subflow for baseline vector store ingestion."""
    logger = get_run_logger()
    
    try:
        logger.info(f"🎯 BASELINE INGESTION START - Version: {experiment_version}")
        logger.info(f"📊 Processing {len(documents)} documents for collection: {collection_name}")
        
        # Use URL/API key directly to avoid client serialization issues
        baseline_vectorstore = QdrantVectorStore.from_documents(
            documents,
            embeddings,
            url=os.getenv("QDRANT_API_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
            prefer_grpc=True,
            collection_name=collection_name
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
        )
        
        # Setup retriever
        child_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size)
        retriever = ParentDocumentRetriever(
            vectorstore=vectorstore,
            docstore=parent_document_store,
            child_splitter=child_splitter,
        )
        
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
            collection_name=collection_name
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
    config: Optional[Dict[str, Any]] = None,
    force_refresh: bool = False,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Master flow orchestrating baseline, parent-child, and semantic ingestion subflows."""
    logger = get_run_logger()
    
    # Use default config if none provided
    if config is None:
        config = DEFAULT_CONFIG.copy()
    
    logger.info(f"🚀 MASTER INGESTION FLOW START - Version: {experiment_version}")
    logger.info(f"📋 Config: {config}")
    
    try:
        # === PHASE 1: INFRASTRUCTURE SETUP ===
        logger.info("🔧 Phase 1: Infrastructure Setup")
        
        # Validate required environment variables first
        required_env_vars = ["QDRANT_API_URL", "OPENAI_API_KEY"]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")
        
        # Log environment setup (API key is optional for local development)
        qdrant_url = os.getenv("QDRANT_API_URL")
        qdrant_key = os.getenv("QDRANT_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        logger.info(f"🔗 Qdrant URL: {qdrant_url}")
        logger.info(f"🔑 Qdrant API Key: {'Set' if qdrant_key else 'Not set (local mode)'}")
        logger.info(f"🤖 OpenAI API Key: {'Set' if openai_key else 'ERROR - This should not happen!'}")
        
        # Setup infrastructure in parallel
        redis_future = setup_redis_store.submit(config["redis_url"])
        collection_names = [
            config["baseline_collection"],
            config["parent_child_collection"], 
            config["semantic_collection"]
        ]
        qdrant_future = setup_qdrant_store.submit(
            collection_names, 
            config["vector_size"], 
            config["distance_metric"]
        )
        embeddings_future = create_embeddings.submit(config["embedding_model"])
        
        # Await infrastructure setup (proper async pattern)
        redis_store = redis_future.result()
        qdrant_client = qdrant_future.result()
        embeddings = embeddings_future.result()
        
        # === PHASE 3: DATA LOADING (Moved before Phase 2) ===
        logger.info("📄 Phase 3: Data Loading")
        
        docs_future = load_documents.submit(config["data_dir"])
        documents = docs_future.result()
        
        if not documents:
            raise ValueError("No documents loaded - check data directory and files")
        
        semantic_docs_future = create_semantic_chunks.submit(documents, embeddings)
        semantic_documents = semantic_docs_future.result()

        # === PHASE 2: DATA ASSESSMENT (Now after Data Loading) ===
        logger.info("📊 Phase 2: Data Assessment")
        
        data_status = await check_existing_data(redis_store, qdrant_client, config)
        
        # Enhanced data check with document count validation
        complete_ingestion = (
            data_status["baseline_count"] >= len(documents) and
            data_status["parent_child_count"] >= len(documents) and  
            data_status["semantic_count"] >= len(semantic_documents) and
            data_status["redis_count"] >= len(documents)
        )
        
        if complete_ingestion and not force_refresh:
            logger.info("⚠️  Complete data already exists. Use force_refresh=True to overwrite.")
            
            # Still validate existing data
            validation_result = await validate_ingestion(
                redis_store, qdrant_client, config
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
        
        # Call subflows directly to get coroutines
        baseline_coro = baseline_ingest_flow(
            documents, embeddings, config["baseline_collection"], experiment_version
        )
        parent_child_coro = parent_child_ingest_flow(
            documents, redis_store, qdrant_client, embeddings, 
            config["parent_child_collection"], config["chunk_size"], experiment_version
        )
        semantic_coro = semantic_ingest_flow(
            semantic_documents, embeddings, config["semantic_collection"], experiment_version
        )
        
        # Await all subflow coroutines concurrently using asyncio.gather
        baseline_result, parent_child_result, semantic_result = await asyncio.gather(
            baseline_coro,
            parent_child_coro,
            semantic_coro
        )
        
        # === PHASE 5: VALIDATION ===
        logger.info("✅ Phase 5: Final Validation")
        
        validation_result = await validate_ingestion(
            redis_store, qdrant_client, config, len(documents)
        )
        
        # === PHASE 6: REPORTING ===
        logger.info("📋 Phase 6: Reporting")
        
        # Create comprehensive summary artifact
        summary = f"""# 🎯 Three-Tier RAG Ingestion Complete - {experiment_version}

## 📊 Experiment Configuration
- **Version**: {experiment_version}
- **Baseline Collection**: {config['baseline_collection']}
- **Parent-Child Collection**: {config['parent_child_collection']} 
- **Semantic Collection**: {config['semantic_collection']}
- **Chunk Size**: {config['chunk_size']}
- **Embedding Model**: {config['embedding_model']}

## 📈 Processing Summary  
- **Documents Processed**: {len(documents)}
- **Semantic Chunks Created**: {len(semantic_documents)}

## 🎯 Subflow Results

### Baseline Vector Store
- **Collection**: {baseline_result['collection_name']}
- **Documents**: {baseline_result['documents_ingested']}
- **Final Vectors**: {baseline_result['final_count']}
- **Version**: {baseline_result['experiment_version']}

### Parent-Child Architecture  
- **Collection**: {parent_child_result['collection_name']}
- **Documents**: {parent_child_result['documents_ingested']}
- **Redis Parents**: {parent_child_result['redis_final_count']}
- **Child Vectors**: {parent_child_result['qdrant_final_count']}
- **Ingestion Time**: {parent_child_result['ingestion_time_seconds']:.2f}s
- **Chunk Size**: {parent_child_result['chunk_size']}
- **Version**: {parent_child_result['experiment_version']}

### Semantic Vector Store
- **Collection**: {semantic_result['collection_name']} 
- **Chunks**: {semantic_result['chunks_ingested']}
- **Final Vectors**: {semantic_result['final_count']}
- **Version**: {semantic_result['experiment_version']}

## ✅ Validation: {'PASSED' if validation_result['validation_passed'] else 'FAILED'}

## 🕐 Completed: {datetime.now().isoformat()}

---
*Ready for retrieval method comparison in notebook!*
"""
        
        # Ensure artifact key is compliant: lowercase, numbers, dashes only
        safe_key_version = experiment_version.lower().replace('.', '-').replace(' ', '-').replace('_', '-')

        await create_markdown_artifact(
            key=f"three-tier-ingestion-{safe_key_version}",
            markdown=summary,
            description=f"Three-Tier RAG Ingestion Summary - {experiment_version}"
        )
        
        final_result = {
            "status": "completed",
            "experiment_version": experiment_version,
            "config": config,
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
    config: Optional[Dict[str, Any]] = None,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Run only baseline ingestion subflow."""
    if config is None:
        config = DEFAULT_CONFIG.copy()
        
    embeddings = await create_embeddings(config["embedding_model"])
    documents = await load_documents(config["data_dir"])
    
    return await baseline_ingest_flow(
        documents, embeddings, config["baseline_collection"], experiment_version
    )

async def run_semantic_only(
    config: Optional[Dict[str, Any]] = None,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Run only semantic ingestion subflow."""
    if config is None:
        config = DEFAULT_CONFIG.copy()
        
    embeddings = await create_embeddings(config["embedding_model"])
    documents = await load_documents(config["data_dir"])
    semantic_documents = await create_semantic_chunks(documents, embeddings)
    
    return await semantic_ingest_flow(
        semantic_documents, embeddings, config["semantic_collection"], experiment_version
    )

async def run_parent_child_only(
    config: Optional[Dict[str, Any]] = None,
    experiment_version: str = "v1.0"
) -> Dict[str, Any]:
    """Run only parent-child ingestion subflow."""
    if config is None:
        config = DEFAULT_CONFIG.copy()
        
    redis_store = await setup_redis_store(config["redis_url"])
    qdrant_client = await setup_qdrant_store(
        [config["parent_child_collection"]],
        config["vector_size"], 
        config["distance_metric"]
    )
    embeddings = await create_embeddings(config["embedding_model"])
    documents = await load_documents(config["data_dir"])
    
    return await parent_child_ingest_flow(
        documents, redis_store, qdrant_client, embeddings,
        config["parent_child_collection"], config["chunk_size"], experiment_version
    )

if __name__ == "__main__":
    # Run the master flow (one command for everything)
    asyncio.run(master_ingestion_flow()) 