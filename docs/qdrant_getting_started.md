Here’s a companion Markdown file you can add alongside your notebook—name it **`SETUP_QDRANT.md`**:

````markdown
# Setting Up Qdrant for LangChain Retrieval Methods

This guide walks you through configuring a Qdrant vector database for use with the `retriever_method_comparison.ipynb` notebook.

## Prerequisites

- **Python 3.11+** environment  
- Install dependencies:
  ```bash
  pip install qdrant-client langchain-qdrant python-dotenv
````

* Copy and edit your environment file:

  ```bash
  cp .env.example .env
  ```
* In `.env`, add:

  ```dotenv
  QDRANT_API_URL=      # e.g. http://localhost:6333 or https://<your-cluster>.qdrant.cloud
  QDRANT_API_KEY=      # leave blank for local; set your Qdrant Cloud API key otherwise
  ```

## Option A: Run Qdrant Locally via Docker

```bash
docker pull qdrant/qdrant
docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage" \
  qdrant/qdrant
```

* **REST API**: `http://localhost:6333`
* **gRPC API**: `localhost:6334`
* **Dashboard**: `http://localhost:6333/dashboard`

Health check:

```bash
curl http://localhost:6333/health
```

## Option B: Use Qdrant Cloud

1. Sign up at [Qdrant Cloud](https://cloud.qdrant.io) and create a cluster.
2. Copy your **Cluster URL** and **API Key** from the dashboard.
3. Update your `.env`:

   ```dotenv
   QDRANT_API_URL=https://<yourcluster>.qdrant.cloud
   QDRANT_API_KEY=<your-api-key>
   ```

## Notebook Collection Names

This notebook creates (or uses) three collections by default:

* `johnwick_baseline`
* `johnwick_parent`
* `johnwick_semantic`

If you’d rather drive them via env-vars, add to `.env`:

```dotenv
BASELINE_COLLECTION=johnwick_baseline
PARENT_COLLECTION=johnwick_parent
SEMANTIC_COLLECTION=johnwick_semantic
```

Then update the notebook to read, e.g.

```python
collection_name = os.getenv("BASELINE_COLLECTION")
```

## Connecting from Python

```python
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore

load_dotenv()

client = QdrantClient(
    url=os.environ["QDRANT_API_URL"],
    api_key=os.getenv("QDRANT_API_KEY"),
    prefer_grpc=True,
)

# Example: create/load baseline collection
baseline_vs = QdrantVectorStore.from_documents(
    documents,
    embeddings,
    url=os.environ["QDRANT_API_URL"],
    api_key=os.getenv("QDRANT_API_KEY"),
    prefer_grpc=True,
    collection_name=os.getenv("BASELINE_COLLECTION", "johnwick_baseline"),
)
```

## Performance & Best Practices

* **Sharding & Replication**: In production, enable multiple shards/replicas.
* **Quantization**: Use Qdrant’s quantization options to reduce index size & memory.
* **Monitoring**: Expose Prometheus metrics and set up alerting on latency/errors.
* **Backups**: Schedule snapshots or leverage Qdrant Cloud’s auto-backup feature.

---

With Qdrant running and your `.env` configured, just launch the notebook: it will create and populate the collections on first run.
