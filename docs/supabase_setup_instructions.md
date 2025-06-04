# Supabase Setup Instructions for LangChain RAG Pipeline

Follow these step-by-step instructions to set up your Supabase database for the LangChain RAG pipeline.

## Prerequisites

- Supabase account and project ([create one here](https://supabase.com/))
- OpenAI API key ([get one here](https://platform.openai.com/api-keys))
- Python 3.8+ environment

## 1. Database Setup

### Option A: Quick Setup via SQL Editor (Recommended)

1. **Go to SQL Editor**
   - Navigate to your [Supabase Dashboard](https://supabase.com/dashboard)
   - Select your project
   - Go to **SQL Editor** in the sidebar

2. **Use LangChain Quick Start**
   - In the SQL Editor, look for the **Quick start** section
   - Click **LangChain** 
   - Click **Run** to execute the script

   This automatically creates:
   - `pgvector` extension
   - `documents` table with proper schema
   - `match_documents` function for similarity search

3. **Add Custom Tables**
   - After the LangChain quick start, run this additional SQL:

```sql
-- Custom tables for raw document storage and delta tracking
create table if not exists raw_documents (
    doc_id text primary key,
    raw_document jsonb not null,
    content_hash text not null,
    updated_at timestamptz not null default now()
);

-- Indexes for performance
create index if not exists idx_raw_documents_updated_at on raw_documents (updated_at);
create index if not exists idx_raw_documents_content_hash on raw_documents (content_hash);

-- Table for tracking last vector sync timestamps  
create table if not exists index_tracker (
    store_name text primary key,
    last_indexed timestamptz not null
);
```

### Option B: Manual Setup

If you prefer manual setup, run this complete SQL script:

```sql
-- Enable the pgvector extension
create extension if not exists vector;

-- Official LangChain documents table
create table if not exists documents (
    id uuid primary key default gen_random_uuid(),
    content text,
    metadata jsonb,
    embedding vector (1536)
);

-- Official LangChain similarity search function
create or replace function match_documents (
    query_embedding vector (1536),
    filter jsonb default '{}'
) returns table (
    id uuid,
    content text,
    metadata jsonb,
    similarity float
) language plpgsql as $$
#variable_conflict use_column
begin
    return query
    select
        id,
        content,
        metadata,
        1 - (documents.embedding <=> query_embedding) as similarity
    from documents
    where metadata @> filter
    order by documents.embedding <=> query_embedding;
end;
$$;

-- Custom tables for raw storage and delta tracking
create table if not exists raw_documents (
    doc_id text primary key,
    raw_document jsonb not null,
    content_hash text not null,
    updated_at timestamptz not null default now()
);

create index if not exists idx_raw_documents_updated_at on raw_documents (updated_at);
create index if not exists idx_raw_documents_content_hash on raw_documents (content_hash);

create table if not exists index_tracker (
    store_name text primary key,
    last_indexed timestamptz not null
);
```

## 2. Get Your Credentials

### Supabase Credentials

1. **Get Project URL**
   - In your Supabase Dashboard
   - Go to **Settings** → **API**
   - Copy the **Project URL** (looks like `https://your-project.supabase.co`)

2. **Get Service Role Key**
   - In the same **Settings** → **API** page
   - Copy the **service_role** key (not the anon key)
   - ⚠️ **Important**: Use `service_role` key, not `anon` key for LangChain integration

### OpenAI Credentials

3. **Get OpenAI API Key**
   - Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
   - Create a new secret key
   - Copy the key (starts with `sk-`)

## 3. Environment Configuration

Create a `.env` file in your project root:

```bash
# Supabase Configuration
SUPABASE_URL="https://your-project-id.supabase.co"
SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# OpenAI Configuration  
OPENAI_API_KEY="sk-your-openai-key-here"

# Optional: Qdrant for future scenario
QDRANT_URL="http://localhost:6333"
```

**Security Notes:**
- Never commit `.env` files to version control
- Use the `service_role` key for server-side operations
- The `service_role` key bypasses Row Level Security - use carefully

## 4. Python Environment Setup

### Install Required Packages

```bash
pip install langchain-community langchain-openai supabase prefect python-dotenv unstructured qdrant-client
```

### Verify Installation

Create a test script `test_setup.py`:

```python
import os
from dotenv import load_dotenv
from supabase import create_client
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore

load_dotenv()

# Test Supabase connection
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")

if not supabase_url or not supabase_key:
    print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
    exit(1)

try:
    supabase = create_client(supabase_url, supabase_key)
    
    # Test database connection
    result = supabase.table("documents").select("count").execute()
    print("✅ Supabase connection successful")
    
    # Test OpenAI embeddings
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    test_embedding = embeddings.embed_query("test")
    print(f"✅ OpenAI embeddings working (dimension: {len(test_embedding)})")
    
    # Test LangChain SupabaseVectorStore
    vector_store = SupabaseVectorStore(
        client=supabase,
        embedding=embeddings,
        table_name="documents",
        query_name="match_documents"
    )
    print("✅ LangChain SupabaseVectorStore initialized")
    
    print("\n🎉 Setup verification complete!")
    
except Exception as e:
    print(f"❌ Setup error: {e}")
```

Run the test:
```bash
python test_setup.py
```

## 5. Database Schema Verification

Verify your tables were created correctly:

```sql
-- Check if tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('documents', 'raw_documents', 'index_tracker');

-- Check documents table structure
\d documents;

-- Check if match_documents function exists
SELECT routine_name 
FROM information_schema.routines 
WHERE routine_name = 'match_documents';
```

Expected output:
```
     table_name      
--------------------
 documents
 raw_documents
 index_tracker

 routine_name   
---------------
 match_documents
```

## 6. Optional: Qdrant Setup (Future Scenario)

If you plan to use Qdrant for the future scenario:

### Local Qdrant Installation

```bash
# Using Docker
docker run -p 6333:6333 qdrant/qdrant

# Or using pip
pip install qdrant-client
```

### Qdrant Cloud

1. Sign up at [Qdrant Cloud](https://cloud.qdrant.io/)
2. Create a cluster
3. Get your API key and endpoint
4. Update `.env`:
   ```bash
   QDRANT_URL="https://your-cluster.qdrant.cloud"
   QDRANT_API_KEY="your-api-key"
   ```

## 7. Testing the Complete Pipeline

Run the main pipeline to verify everything works:

```bash
python langchain_supabase_rag.py
```

Expected output:
```
✅ Created official LangChain documents table and match_documents function
✅ Created custom raw_documents and index_tracker tables  
✅ Loading 50 Azure URLs...
✅ Loaded 127 documents
✅ Persisted 127 raw documents
✅ Found 127 document deltas since 1970-01-01 00:00:00
✅ Processed 127 deltas to LangChain vector store
✅ LangChain similarity search for 'What is Form Recognizer used for?' (k=3):
1. doc_id=a1b2c3d4..., content=Form Recognizer is a cloud service that uses machine learning...
```

## Troubleshooting

### Common Issues

**Issue**: `extension "vector" does not exist`
```
Solution: Run the LangChain quick start in SQL Editor, or manually:
CREATE EXTENSION IF NOT EXISTS vector;
```

**Issue**: `function match_documents does not exist`
```
Solution: Run the match_documents function creation SQL from step 1
```

**Issue**: `Authentication failed`
```
Solution: Check you're using SUPABASE_SERVICE_KEY (not anon key)
```

**Issue**: `OpenAI rate limits`
```
Solution: The pipeline includes automatic retries. Consider upgrading OpenAI tier if needed.
```

### Verification Queries

Check your setup with these SQL queries:

```sql
-- Check document counts
SELECT 
    (SELECT COUNT(*) FROM documents) as vector_docs,
    (SELECT COUNT(*) FROM raw_documents) as raw_docs,
    (SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL) as embedded_docs;

-- Check recent activity
SELECT store_name, last_indexed 
FROM index_tracker;

-- Test similarity search function
SELECT * FROM match_documents(
    (SELECT embedding FROM documents LIMIT 1),
    '{}'::jsonb
) LIMIT 3;
```

## Next Steps

Once setup is complete:

1. **Run the pipeline**: `python langchain_supabase_rag.py`
2. **Monitor via Prefect**: Start Prefect server for pipeline monitoring
3. **Customize URLs**: Modify Azure URL imports for your specific content
4. **Add scheduling**: Use Prefect or cron for automated runs
5. **Scale up**: Consider connection pooling for production workloads

You're now ready to run the full RAG pipeline with LangChain and Supabase! 🚀

## References and Citations

### Official Documentation

1. **Supabase LangChain Integration**  
   Supabase Docs. "LangChain | Supabase Docs" (2025)  
   https://supabase.com/docs/guides/ai/langchain  
   *Source for LangChain Quick Start setup and match_documents function usage*

2. **LangChain SupabaseVectorStore**  
   LangChain Documentation. "SupabaseVectorStore | 🦜️🔗 Langchain" (2025)  
   https://js.langchain.com/docs/integrations/vectorstores/supabase/  
   *Reference for JavaScript integration patterns and configuration*

3. **LangChain Python Supabase Integration**  
   LangChain Documentation. "Supabase (Postgres) | 🦜️🔗 LangChain" (2025)  
   https://python.langchain.com/docs/integrations/vectorstores/supabase/  
   *Python-specific implementation guidance and examples*

4. **pgvector Extension**  
   pgvector GitHub Repository. "Open-source vector similarity search for Postgres" (2024)  
   https://github.com/pgvector/pgvector  
   *Official source for pgvector installation, configuration, and capabilities*

5. **OpenAI Embeddings API**  
   OpenAI Platform Documentation. "Embeddings Guide" (2025)  
   https://platform.openai.com/docs/guides/embeddings  
   *Reference for text-embedding-3-small model specifications and usage*

6. **Supabase SQL Editor**  
   Supabase Features. "SQL Editor | Supabase Features" (2025)  
   https://supabase.com/features/sql-editor  
   *Documentation for SQL Editor interface and Quick Start functionality*

### Technical References

7. **pgvector Performance and Indexing**  
   PostgreSQL Documentation. "pgvector 0.8.0 Released!" (2024)  
   https://www.postgresql.org/about/news/pgvector-080-released-2952/  
   *Details on latest pgvector features and performance improvements*

8. **Prefect Workflow Orchestration**  
   Prefect Documentation. "Prefect | Modern Workflow Orchestration" (2025)  
   https://www.prefect.io/  
   *Reference for workflow management and pipeline orchestration*

9. **LangChain Community Package**  
   PyPI. "langchain-community" (2025)  
   https://pypi.org/project/langchain-community/  
   *Package versioning and installation requirements*

### Implementation Guides

10. **Supabase Vector Store Tutorial**  
    DataCamp. "pgvector Tutorial: Integrate Vector Search into PostgreSQL" (2024)  
    https://www.datacamp.com/tutorial/pgvector-tutorial  
    *Comprehensive tutorial on pgvector integration and usage patterns*

11. **LangChain Self-Query Retriever**  
    LangChain Documentation. "Supabase | 🦜️🔗 Langchain" (2025)  
    https://js.langchain.com/docs/integrations/retrievers/self_query/supabase/  
    *Advanced querying patterns and metadata filtering examples*

### Community Resources

12. **Supabase Hybrid Search**  
    LangChain Documentation. "Supabase Hybrid Search | 🦜️🔗 Langchain" (2025)  
    https://js.langchain.com/docs/integrations/retrievers/supabase-hybrid/  
    *Implementation guide for combining vector and full-text search*

13. **LangChain x Supabase Blog Post**  
    LangChain Blog. "LangChain x Supabase" (2023)  
    https://blog.langchain.dev/langchain-x-supabase/  
    *Foundational article on LangChain and Supabase integration patterns*

### Key Technical Specifications Referenced

- **pgvector**: v0.8.0 (October 2024) - supports PostgreSQL 13+
- **LangChain Community**: v0.3.24 (May 2025) - latest stable release  
- **OpenAI Embeddings**: text-embedding-3-small (1536 dimensions, $0.00002/1k tokens)
- **Supabase**: PostgreSQL with pgvector extension enabled
- **Python Requirements**: 3.8+ (3.9+ recommended for Prefect)

*Last updated: June 2025*