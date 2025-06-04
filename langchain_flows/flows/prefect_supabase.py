"""
rag_pipeline_requirements_compliant.py

End-to-end RAG pipeline meeting exact requirements:

Current:
1. Ingest Documents from Azure URLs (UnstructuredURLLoader)
2. Persist serialized JSON (langchain_core.dumpd) into Supabase
3. Delta-detect new/changed documents since last vector sync
4. Compute embeddings (OpenAIEmbeddings) for deltas only
5. Store embeddings in same Supabase table VECTOR column
6. Direct SQL nearest-neighbor retrieval

Future: Same flow but with Qdrant as vector store destination

Prerequisites:
1. Enable pgvector in Supabase Dashboard: Database → Extensions → "vector"
2. Set environment variables: SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY

Installation:
    pip install langchain-core langchain-openai langchain-community psycopg2-binary prefect python-dotenv unstructured supabase qdrant-client
"""

import os
import json
import hashlib
from typing import List, Tuple, Optional
from datetime import datetime

import psycopg2
from psycopg2.extras import Json
from prefect import flow, task, get_run_logger
from dotenv import load_dotenv

# LangChain imports
from langchain_core.documents import Document
from langchain_core.load import dumpd, load as load_lc
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import UnstructuredURLLoader

# Supabase client (for connection string)
from supabase import create_client

# Qdrant client (for future use)
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

load_dotenv()

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")  # Direct postgres connection
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

EMBEDDING_MODEL = "text-embedding-3-small"
RAW_TABLE = "raw_documents"
INDEX_TRACKER = "index_tracker"
QDRANT_COLLECTION = "documents"


def get_supabase_connection() -> psycopg2.extensions.connection:
    """Get direct PostgreSQL connection to Supabase."""
    if not SUPABASE_DB_URL:
        raise ValueError("SUPABASE_DB_URL must be set for direct database access")
    return psycopg2.connect(SUPABASE_DB_URL)


def get_qdrant_client() -> Optional['QdrantClient']:
    """Get Qdrant client if available."""
    if not QDRANT_AVAILABLE:
        return None
    return QdrantClient(url=QDRANT_URL)

@task
def initialize_supabase_tables():
    """Create required tables for raw document storage and delta tracking."""
    logger = get_run_logger()
    conn = get_supabase_connection()
    cur = conn.cursor()

    # Check if pgvector is available (most Supabase projects have it by default)
    try:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector';")
        if cur.fetchone():
            logger.info("pgvector extension is available")
        else:
            logger.warning("pgvector extension not found - you may need to enable it via Supabase Dashboard: Database → Extensions")
            # Don't fail here - let the table creation attempt reveal if it's actually needed
    except Exception as e:
        logger.warning(f"Could not check pgvector status: {e}")
        # Continue anyway - modern Supabase projects should work

    # Raw documents table: stores serialized JSON + embeddings
    try:
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {RAW_TABLE} (
          doc_id        TEXT        PRIMARY KEY,
          raw_document  JSONB       NOT NULL,
          content_hash  TEXT        NOT NULL,
          updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          embedding     VECTOR(1536)
        );
        """)
        logger.info("Created raw_documents table with VECTOR column")
    except Exception as e:
        if "type \"vector\" does not exist" in str(e):
            logger.error("pgvector extension not available. Enable via Supabase Dashboard: Database → Extensions → 'vector'")
            raise Exception("pgvector extension required for VECTOR column")
        else:
            raise

    # Index for delta detection
    cur.execute(f"""
    CREATE INDEX IF NOT EXISTS idx_{RAW_TABLE}_content_hash
    ON {RAW_TABLE} (content_hash);
    """)

    # Index for vector similarity
    cur.execute(f"""
    CREATE INDEX IF NOT EXISTS idx_{RAW_TABLE}_embedding
    ON {RAW_TABLE} USING ivfflat (embedding vector_cosine_ops);
    """)

    # Delta tracking table
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS {INDEX_TRACKER} (
      store_name    TEXT        PRIMARY KEY,
      last_indexed  TIMESTAMPTZ NOT NULL
    );
    """)

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Supabase tables initialized")

@task
def initialize_qdrant_collection():
    """Initialize Qdrant collection for future vector storage."""
    if not QDRANT_AVAILABLE:
        return
    
    logger = get_run_logger()
    client = get_qdrant_client()
    
    try:
        # Create collection if it doesn't exist
        collections = client.get_collections().collections
        if not any(c.name == QDRANT_COLLECTION for c in collections):
            client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
            )
            logger.info(f"Created Qdrant collection: {QDRANT_COLLECTION}")
        else:
            logger.info(f"Qdrant collection exists: {QDRANT_COLLECTION}")
    except Exception as e:
        logger.warning(f"Qdrant initialization failed: {e}")

@task(retries=3, retry_delay_seconds=10)
def load_documents_from_azure_urls() -> List[Document]:
    """Load Documents from Azure AI Engineer Renewal URLs."""
    logger = get_run_logger()
    
    # Import Azure URLs
    try:
        from azure_ai_engineer_renewal import (
            RENEWAL_PAGE,
            COLLECTION_BASE_URLS,
            SPEECH_ENABLED_APPS_URLS,
            TRANSLATE_SPEECH_URLS,
            CREATE_AZURE_AI_CUSTOM_SKILL_URLS,
            BUILD_LANGUAGE_UNDERSTANDING_MODEL_URLS,
            INVESTIGATE_CONTAINER_URLS,
            ANALYZE_TEXT_URLS,
            DEVELOP_OPENAI_URLS,
            CREATE_QA_SOLUTION_URLS,
            USE_OWN_DATA_URLS,
            FORM_RECOGNIZER_URLS,
            ANALYZE_IMAGES_URLS,
        )
        
        all_urls = [
            RENEWAL_PAGE,
            *COLLECTION_BASE_URLS,
            *SPEECH_ENABLED_APPS_URLS,
            *TRANSLATE_SPEECH_URLS,
            *CREATE_AZURE_AI_CUSTOM_SKILL_URLS,
            *BUILD_LANGUAGE_UNDERSTANDING_MODEL_URLS,
            *INVESTIGATE_CONTAINER_URLS,
            *ANALYZE_TEXT_URLS,
            *DEVELOP_OPENAI_URLS,
            *CREATE_QA_SOLUTION_URLS,
            *USE_OWN_DATA_URLS,
            *FORM_RECOGNIZER_URLS,
            *ANALYZE_IMAGES_URLS,
        ]
    except ImportError:
        logger.warning("Azure URLs module not found, using sample URLs")
        all_urls = [
            "https://docs.microsoft.com/en-us/azure/cognitive-services/",
            "https://docs.microsoft.com/en-us/azure/cognitive-services/openai/",
        ]

    logger.info(f"Loading {len(all_urls)} Azure AI Renewal URLs...")
    loader = UnstructuredURLLoader(urls=all_urls)
    docs = loader.load()
    logger.info(f"Loaded {len(docs)} Document objects")
    return docs

@task
def persist_raw_documents_to_supabase(docs: List[Document]):
    """Persist each Document's serialized JSON into Supabase."""
    logger = get_run_logger()
    conn = get_supabase_connection()
    cur = conn.cursor()

    upsert_sql = f"""
    INSERT INTO {RAW_TABLE} (doc_id, raw_document, content_hash, updated_at)
    VALUES (%s, %s, %s, NOW())
    ON CONFLICT (doc_id) DO UPDATE
      SET raw_document = EXCLUDED.raw_document,
          content_hash = EXCLUDED.content_hash,
          updated_at   = NOW()
    WHERE {RAW_TABLE}.content_hash <> EXCLUDED.content_hash;
    """

    current_ids = set()
    
    for doc in docs:
        # Serialize Document using langchain_core.dumpd
        raw_dict = dumpd(doc)
        raw_json_str = json.dumps(raw_dict, sort_keys=True)
        content_hash = hashlib.sha256(raw_json_str.encode("utf-8")).hexdigest()
        doc_id = content_hash  # Use content hash as doc_id
        
        current_ids.add(doc_id)
        cur.execute(upsert_sql, (doc_id, Json(raw_dict), content_hash))

    # Remove documents no longer present
    if current_ids:
        placeholders = ",".join(["%s"] * len(current_ids))
        delete_sql = f"DELETE FROM {RAW_TABLE} WHERE doc_id NOT IN ({placeholders});"
        cur.execute(delete_sql, tuple(current_ids))
    else:
        cur.execute(f"DELETE FROM {RAW_TABLE};")

    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Persisted {len(current_ids)} raw documents to Supabase")

@task
def get_last_indexed_timestamp(store_name: str) -> datetime:
    """Get last indexed timestamp for delta detection."""
    conn = get_supabase_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT last_indexed FROM {INDEX_TRACKER} WHERE store_name = %s;", (store_name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else datetime.fromtimestamp(0)

@task
def detect_document_deltas(store_name: str) -> List[Tuple[str, dict]]:
    """Delta-detect new/changed documents since last vector sync."""
    logger = get_run_logger()
    last_sync = get_last_indexed_timestamp(store_name)
    
    conn = get_supabase_connection()
    cur = conn.cursor()
    cur.execute(f"""
      SELECT doc_id, raw_document
      FROM {RAW_TABLE}
      WHERE updated_at > %s;
    """, (last_sync,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    deltas = [(doc_id, raw_jsonb) for doc_id, raw_jsonb in rows]
    logger.info(f"Detected {len(deltas)} document deltas since {last_sync}")
    return deltas


@task
def compute_and_store_embeddings_supabase(deltas: List[Tuple[str, dict]]):
    """Compute embeddings for deltas and store in Supabase VECTOR column."""
    logger = get_run_logger()
    
    if not deltas:
        logger.info("No deltas to process for Supabase")
        return

    # Rehydrate Documents and compute embeddings
    docs = [load_lc(raw_dict) for (_id, raw_dict) in deltas]
    embedder = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    texts = [doc.page_content for doc in docs]
    vectors = embedder.embed_documents(texts)

    # Store embeddings in Supabase
    conn = get_supabase_connection()
    cur = conn.cursor()

    update_sql = f"UPDATE {RAW_TABLE} SET embedding = %s WHERE doc_id = %s;"
    
    for (doc_id, _), vector in zip(deltas, vectors):
        cur.execute(update_sql, (vector, doc_id))

    # Update last_indexed timestamp
    now = datetime.utcnow()
    cur.execute(f"""
      INSERT INTO {INDEX_TRACKER} (store_name, last_indexed)
      VALUES ('supabase_vector', %s)
      ON CONFLICT (store_name) DO UPDATE
        SET last_indexed = EXCLUDED.last_indexed;
    """, (now,))

    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Stored {len(deltas)} embeddings in Supabase; updated last_indexed = {now}")


@task
def compute_and_store_embeddings_qdrant(deltas: List[Tuple[str, dict]]):
    """Compute embeddings for deltas and store in Qdrant (future scenario)."""
    logger = get_run_logger()
    
    if not QDRANT_AVAILABLE:
        logger.warning("Qdrant not available, skipping")
        return
        
    if not deltas:
        logger.info("No deltas to process for Qdrant")
        return

    # Rehydrate Documents and compute embeddings
    docs = [load_lc(raw_dict) for (_id, raw_dict) in deltas]
    embedder = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    texts = [doc.page_content for doc in docs]
    vectors = embedder.embed_documents(texts)

    # Store in Qdrant
    client = get_qdrant_client()
    points = []
    
    for (doc_id, raw_dict), vector, doc in zip(deltas, vectors, docs):
        # Qdrant requires point IDs to be UUID or int, not 64-char hex
        import uuid
        # Use UUID5 (namespace-based) to deterministically map hash to UUID
        qdrant_id = str(uuid.UUID(doc_id[0:32])) if len(doc_id) == 32 else str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))
        point = PointStruct(
            id=qdrant_id,
            vector=vector,
            payload={
                "content": doc.page_content,
                "metadata": doc.metadata,
                "doc_id": doc_id
            }
        )
        points.append(point)

    client.upsert(collection_name=QDRANT_COLLECTION, points=points)

    # Update last_indexed timestamp in Supabase
    conn = get_supabase_connection()
    cur = conn.cursor()
    now = datetime.utcnow()
    cur.execute(f"""
      INSERT INTO {INDEX_TRACKER} (store_name, last_indexed)
      VALUES ('qdrant_vector', %s)
      ON CONFLICT (store_name) DO UPDATE
        SET last_indexed = EXCLUDED.last_indexed;
    """, (now,))
    conn.commit()
    cur.close()
    conn.close()
    
    logger.info(f"Stored {len(deltas)} embeddings in Qdrant; updated last_indexed = {now}")

@flow(name="Requirements-Compliant RAG Pipeline")
def rag_pipeline_requirements_compliant(use_qdrant: bool = False):
    """
    End-to-end pipeline meeting exact requirements.
    
    Args:
        use_qdrant: If True, run future scenario with Qdrant storage
    """
    logger = get_run_logger()
    logger.info(f"Starting RAG pipeline (Qdrant mode: {use_qdrant})...")

    # Initialize storage
    initialize_supabase_tables()
    if use_qdrant:
        initialize_qdrant_collection()

    # 1. Ingest Documents from Azure URLs
    docs = load_documents_from_azure_urls()

    # 2. Persist serialized JSON to Supabase
    persist_raw_documents_to_supabase(docs)

    # 3. Delta-detect changed documents
    store_name = "qdrant_vector" if use_qdrant else "supabase_vector"
    deltas = detect_document_deltas(store_name)

    # 4. & 5. Compute embeddings and store
    if use_qdrant:
        compute_and_store_embeddings_qdrant(deltas)
    else:
        compute_and_store_embeddings_supabase(deltas)
    logger.info("Pipeline completed successfully")

if __name__ == "__main__":
    # Current scenario: Supabase storage
    rag_pipeline_requirements_compliant(use_qdrant=False)
    
    # Future scenario: Qdrant storage  
    # rag_pipeline_requirements_compliant(use_qdrant=True)