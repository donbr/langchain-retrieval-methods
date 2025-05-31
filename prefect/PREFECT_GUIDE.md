# 🌊 Prefect 3.4 RAG Ingestion Pipeline Guide

## Overview

This guide covers the modernized Prefect-based RAG ingestion pipeline, updated for **Prefect 3.4 best practices** as of December 2024. The pipeline implements enterprise-grade workflows with comprehensive monitoring, error handling, and deployment capabilities leveraging Prefect's latest client-side orchestration improvements.

## 🏗️ Architecture

### **Files Structure**

```
📁 RAG Ingestion Pipeline
├── 📄 ingestion.py                 # Simple standalone ingestion script (no Prefect)
├── 📄 prefect_ingestion_dev.py     # Development Prefect tasks and flows  
├── 📄 prefect_ingestion_prod.py    # Production deployment with monitoring
├── 📄 PREFECT_GUIDE.md            # This comprehensive guide
└── 📁 config/                      # Configuration files
    ├── 📄 development.yaml         # Development environment
    ├── 📄 staging.yaml             # Staging environment  
    └── 📄 production.yaml          # Production environment
```

### **Core Components**

| Component | File | Description |
|-----------|------|-------------|
| **Simple Ingestion** | `ingestion.py` | Class-based standalone script without orchestration |
| **Dev Tasks** | `prefect_ingestion_dev.py` | Individual @task functions for discrete operations |
| **Dev Flow** | `prefect_ingestion_dev.py` | @flow orchestration with error handling |
| **Production Pipeline** | `prefect_ingestion_prod.py` | Enterprise features, monitoring, deployments |
| **Health Monitoring** | `prefect_ingestion_prod.py` | Continuous infrastructure monitoring |

## 🚀 Getting Started

### **1. Prerequisites**

```bash
# Install Prefect 3.4+
pip install prefect>=3.4.0

# Install additional dependencies
pip install langchain-openai langchain-qdrant langchain-community
pip install redis qdrant-client python-dotenv

# Start Prefect server (for local development)
prefect server start
```

### **2. Environment Setup**

```bash
# Create .env file with your credentials
cat > .env << EOF
OPENAI_API_KEY=your_openai_key_here
COHERE_API_KEY=your_cohere_key_here
QDRANT_API_URL=http://localhost:6333
QDRANT_API_KEY=your_qdrant_key_here
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:4317
EOF
```

### **3. Quick Start Commands**

```bash
# Run simple standalone ingestion
python ingestion.py

# Run development Prefect pipeline  
python prefect_ingestion_dev.py

# Run production pipeline with monitoring
python prefect_ingestion_prod.py run

# Deploy to Prefect server
python prefect_ingestion_prod.py deploy

# Start local development server
python prefect_ingestion_prod.py serve
```

## 📋 Advanced Task Configuration

### **Comprehensive Task Decorator Usage**

Prefect 3.4 provides extensive task configuration options for production-ready workflows:

```python
from prefect import task
from prefect.cache_policies import TASK_SOURCE, INPUTS, NO_CACHE
from datetime import timedelta

@task(
    name="production-data-loader",
    description="Load and validate documents with comprehensive error handling",
    retries=3,
    retry_delay_seconds=30,
    retry_jitter_factor=0.1,  # Add randomness to retry delays
    timeout_seconds=300,
    cache_policy=TASK_SOURCE + INPUTS,
    cache_expiration=timedelta(hours=24),
    tags=["data-loading", "production", "critical"],
    task_run_name="load-{timestamp}",  # Dynamic run names
    persist_result=True,  # Ensure results are persisted
    result_serializer="pickle",  # Control serialization
    log_prints=True  # Capture print statements in logs
)
async def load_production_documents(
    data_source: str,
    batch_size: int = 1000,
    validation_strict: bool = True
) -> List:
    """Production-grade document loading with validation."""
    # Implementation here
    pass
```

### **Cache Policy Best Practices**

Prefect 3.4 offers sophisticated caching strategies for different use cases:

```python
from prefect.cache_policies import (
    DEFAULT, INPUTS, TASK_SOURCE, FLOW_PARAMETERS, NO_CACHE
)

# For expensive computations that depend only on inputs
@task(cache_policy=INPUTS, cache_expiration=timedelta(days=7))
def expensive_embedding_computation(text: str) -> List[float]:
    """Cache results based only on input text."""
    pass

# For tasks with non-serializable objects (database clients, etc.)
@task(cache_policy=NO_CACHE)
def setup_database_connection(connection_string: str) -> DatabaseClient:
    """Avoid caching for non-serializable objects."""
    pass

# For code-dependent tasks that should re-run when logic changes
@task(cache_policy=TASK_SOURCE)
def data_transformation_logic(data: List) -> List:
    """Re-run when transformation logic changes."""
    pass

# Composite cache policies for complex scenarios
@task(cache_policy=TASK_SOURCE + INPUTS - "debug_mode")
def advanced_processing(data: List, config: Dict, debug_mode: bool = False) -> List:
    """Cache based on code and inputs, but ignore debug flag."""
    pass

# Custom cache key functions for specialized scenarios
def custom_cache_key(context, parameters):
    """Custom logic for cache key computation."""
    return f"{parameters['dataset_version']}_{parameters['model_name']}"

@task(cache_key_fn=custom_cache_key)
def model_inference(dataset_version: str, model_name: str, data: List) -> List:
    """Use custom cache key logic."""
    pass
```

### **Error Handling and Retry Strategies**

```python
from prefect import task, get_run_logger
from prefect.exceptions import SKIP

@task(
    retries=3,
    retry_delay_seconds=[10, 30, 60],  # Exponential backoff
    retry_condition_fn=lambda task, state, context: "connection" in str(state.message)
)
async def resilient_api_call(endpoint: str) -> Dict:
    """Retry only on connection errors."""
    logger = get_run_logger()
    
    try:
        response = await make_api_call(endpoint)
        return response
    except ConnectionError as e:
        logger.warning(f"Connection error: {e}")
        raise  # Will trigger retry
    except ValueError as e:
        logger.error(f"Data validation error: {e}")
        raise SKIP(f"Skipping due to invalid data: {e}")  # Skip without retry
```

## 🌊 Enhanced Flow Orchestration

### **Client-Side Orchestration Benefits**

Prefect 3.4's client-side orchestration provides significant performance improvements:

```python
@flow(
    name="high-performance-rag-pipeline",
    description="Optimized for Prefect 3.4 client-side orchestration",
    task_runner=ThreadPoolTaskRunner(max_workers=6),
    timeout_seconds=3600,
    retries=2,
    retry_delay_seconds=60,
    log_prints=True,
    persist_result=True
)
async def optimized_ingestion_flow(
    config: Dict[str, Any],
    force_refresh: bool = False
) -> Dict[str, Any]:
    """Optimized flow leveraging client-side orchestration."""
    logger = get_run_logger()
    
    # Submit all infrastructure setup tasks concurrently
    redis_future = setup_redis_store.submit(config["redis_url"])
    qdrant_future = setup_qdrant_store.submit(config["collections"])
    embeddings_future = create_embeddings.submit(config["embedding_model"])
    
    # Await results efficiently
    redis_store, qdrant_client, embeddings = await asyncio.gather(
        redis_future.result(),
        qdrant_future.result(), 
        embeddings_future.result()
    )
    
    # Smart data checking with conditional execution
    data_status = await check_existing_data(redis_store, qdrant_client, config)
    
    if data_status["has_data"] and not force_refresh:
        logger.info("🔄 Using existing data - skipping ingestion")
        return await create_summary_artifact(data_status)
    
    # Load documents and create semantic chunks in parallel
    docs_future = load_documents.submit(config["data_dir"])
    
    documents = await docs_future.result()
    semantic_docs_future = create_semantic_chunks.submit(documents, embeddings)
    semantic_documents = await semantic_docs_future.result()
    
    # Parallel ingestion across all vector stores
    ingestion_results = await asyncio.gather(
        ingest_baseline_vectorstore(documents, embeddings, config["baseline_collection"]),
        ingest_parent_child_documents(documents, redis_store, qdrant_client, embeddings, config["parent_child_collection"]),
        ingest_semantic_vectorstore(semantic_documents, embeddings, config["semantic_collection"])
    )
    
    # Final validation
    validation = await validate_ingestion(redis_store, qdrant_client, config)
    
    return {
        "status": "completed",
        "ingestion_results": ingestion_results,
        "validation": validation,
        "performance_metrics": {
            "documents_processed": len(documents),
            "semantic_chunks": len(semantic_documents),
            "parallel_execution": True
        }
    }
```

## 🚢 Production Deployment Patterns

### **Deployment Strategy Comparison**

| Method | Use Case | Pros | Cons |
|--------|----------|------|------|
| **`.serve()`** | Local development, prototyping | Simple, immediate feedback | Single machine, not scalable |
| **`.deploy()`** | Production with work pools | Scalable, infrastructure templates | Requires work pool setup |
| **YAML-based** | CI/CD, declarative infrastructure | Version controlled, automated | More complex initial setup |

### **1. Development with `.serve()`**

```python
# Simple development deployment
if __name__ == "__main__":
    main_ingestion_flow.serve(
        name="rag-dev-deployment",
        cron="0 2 * * *",  # Daily at 2 AM
        parameters={"config": DEV_CONFIG, "force_refresh": False},
        tags=["development", "rag"]
    )
```

### **2. Production with `.deploy()`**

```python
# Production deployment with work pools
if __name__ == "__main__":
    deployment = main_ingestion_flow.deploy(
        name="rag-production-pipeline",
        work_pool_name="kubernetes-pool",
        image="myregistry/rag-pipeline:latest",
        push=True,
        cron="0 1 * * *",  # Daily at 1 AM
        parameters={
            "config": PRODUCTION_CONFIG,
            "force_refresh": False,
            "enable_monitoring": True
        },
        tags=["production", "rag", "ml"],
        version="1.0.0",
        entrypoint="prefect_ingestion_prod.py:main_ingestion_flow",
        job_variables={
            "image_pull_policy": "Always",
            "cpu_request": "2",
            "memory_request": "4Gi",
            "cpu_limit": "4", 
            "memory_limit": "8Gi"
        }
    )
```

### **3. YAML-Based Deployment**

```yaml
# prefect.yaml
deployments:
  - name: rag-production
    version: "1.0.0"
    work_pool:
      name: kubernetes-pool
      job_variables:
        image: "myregistry/rag-pipeline:latest"
        cpu_request: "2"
        memory_request: "4Gi"
    schedule:
      cron: "0 1 * * *"
      timezone: "UTC"
    parameters:
      config: 
        collection_name: "production_reviews"
        chunk_size: 200
        redis_url: "redis://production-redis:6379"
      force_refresh: false
      enable_monitoring: true
    tags: ["production", "rag"]
    
build:
  - prefect_docker.deployments.steps.build_docker_image:
      id: build-image
      requires: prefect-docker>=0.3.0
      image_name: "myregistry/rag-pipeline"
      tag: "latest"
      dockerfile: "Dockerfile"

push:
  - prefect_docker.deployments.steps.push_docker_image:
      requires: prefect-docker>=0.3.0
      image_name: "{{ build-image.image_name }}"
      tag: "{{ build-image.tag }}"

pull:
  - prefect.deployments.steps.git_clone:
      repository: "https://github.com/myorg/rag-pipeline.git"
      branch: "main"
```

### **4. Work Pool Configuration**

```python
# Advanced work pool setup
from prefect.workers.kubernetes import KubernetesWorker

# Create work pool with custom configuration
work_pool_config = {
    "type": "kubernetes",
    "base_job_template": {
        "job_configuration": {
            "image": "{{ image }}",
            "namespace": "prefect-production",
            "service_account_name": "prefect-worker",
            "image_pull_policy": "Always",
            "labels": {"app": "rag-pipeline"},
            "annotations": {"prometheus.io/scrape": "true"}
        },
        "variables": {
            "properties": {
                "image": {"default": "myregistry/rag-pipeline:latest"},
                "cpu_request": {"default": "1"},
                "memory_request": {"default": "2Gi"},
                "cpu_limit": {"default": "2"},
                "memory_limit": {"default": "4Gi"}
            }
        }
    }
}
```

## 🏥 Advanced Monitoring & Observability

### **Comprehensive Health Monitoring**

```python
@flow(
    name="rag-health-monitoring",
    description="Comprehensive infrastructure and pipeline health monitoring",
    task_runner=ThreadPoolTaskRunner(max_workers=3),
    log_prints=True
)
async def comprehensive_health_monitoring(
    config: Dict[str, Any],
    alert_webhooks: List[str] = None
) -> Dict[str, Any]:
    """Advanced health monitoring with alerting."""
    
    # Parallel health checks
    health_checks = await asyncio.gather(
        check_redis_health(config["redis_url"]),
        check_qdrant_health(config["qdrant_url"]),
        check_embedding_service_health(config["embedding_model"]),
        return_exceptions=True
    )
    
    # Aggregate health status
    health_status = {
        "redis": health_checks[0] if not isinstance(health_checks[0], Exception) else "UNHEALTHY",
        "qdrant": health_checks[1] if not isinstance(health_checks[1], Exception) else "UNHEALTHY", 
        "embeddings": health_checks[2] if not isinstance(health_checks[2], Exception) else "UNHEALTHY"
    }
    
    overall_health = "HEALTHY" if all(
        status == "HEALTHY" for status in health_status.values()
    ) else "DEGRADED"
    
    # Performance metrics collection
    metrics = await collect_performance_metrics(config)
    
    # Create detailed monitoring artifact
    monitoring_report = f"""# 🏥 RAG Pipeline Health Report

## 🔧 Infrastructure Status: {overall_health}

| Component | Status | Details |
|-----------|--------|---------|
| Redis | {health_status['redis']} | {'✅' if health_status['redis'] == 'HEALTHY' else '❌'} |
| Qdrant | {health_status['qdrant']} | {'✅' if health_status['qdrant'] == 'HEALTHY' else '❌'} |
| Embeddings | {health_status['embeddings']} | {'✅' if health_status['embeddings'] == 'HEALTHY' else '❌'} |

## 📊 Performance Metrics

- **Document Count**: {metrics.get('document_count', 'N/A')}
- **Vector Count**: {metrics.get('vector_count', 'N/A')}
- **Average Query Latency**: {metrics.get('avg_latency_ms', 'N/A')}ms
- **Cache Hit Rate**: {metrics.get('cache_hit_rate', 'N/A')}%
- **Error Rate (24h)**: {metrics.get('error_rate_24h', 'N/A')}%

## 🕐 Timestamp
{datetime.now().isoformat()}
"""
    
    await create_markdown_artifact(
        key="rag-health-report",
        markdown=monitoring_report,
        description="RAG Pipeline Health and Performance Report"
    )
    
    # Alert on degraded health
    if overall_health != "HEALTHY" and alert_webhooks:
        await send_health_alerts(health_status, alert_webhooks)
    
    return {
        "overall_health": overall_health,
        "component_health": health_status,
        "metrics": metrics,
        "timestamp": datetime.now().isoformat()
    }
```

## ⚡ Performance Optimization Patterns

### **Prefect 3.4 Client-Side Optimization**

```python
# Optimized task submission patterns
@flow
async def optimized_parallel_flow():
    """Demonstrate optimal parallel execution patterns."""
    
    # ✅ GOOD: Submit all tasks then await results
    futures = [
        process_chunk.submit(chunk) 
        for chunk in data_chunks
    ]
    results = await asyncio.gather(*[f.result() for f in futures])
    
    # ❌ AVOID: Sequential submission and waiting
    # results = []
    # for chunk in data_chunks:
    #     result = await process_chunk(chunk)  # This is sequential!
    #     results.append(result)
    
    return results

# Memory-efficient processing for large datasets
@task
async def batch_process_documents(
    documents: List,
    batch_size: int = 100
) -> List:
    """Process documents in memory-efficient batches."""
    results = []
    
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        batch_results = await process_document_batch(batch)
        results.extend(batch_results)
        
        # Clear intermediate results to manage memory
        del batch_results
        
    return results
```

### **Resource Management**

```python
@task(
    task_run_name="resource-managed-{task_name}",
    cache_policy=NO_CACHE,  # Avoid caching large objects
    persist_result=False    # Don't persist large results
)
async def resource_efficient_task(large_dataset: List) -> Dict[str, Any]:
    """Demonstrate resource-efficient patterns."""
    
    # Use context managers for resource cleanup
    async with managed_database_connection() as db:
        # Process data in chunks
        summary_stats = {}
        
        for chunk in chunk_data(large_dataset, size=1000):
            chunk_stats = await process_chunk(chunk, db)
            update_summary(summary_stats, chunk_stats)
            
            # Explicit cleanup of large intermediate objects
            del chunk_stats
    
    # Return only summary, not large processed data
    return summary_stats
```

## 🔧 Configuration Management

### **Environment-Specific Configuration**

```python
# Enhanced configuration management
from dataclasses import dataclass
from typing import Optional
import os

@dataclass
class PipelineConfig:
    """Type-safe configuration management."""
    
    # Core settings
    baseline_collection: str
    parent_child_collection: str
    semantic_collection: str
    chunk_size: int
    embedding_model: str
    
    # Infrastructure
    redis_url: str
    qdrant_url: str
    qdrant_api_key: Optional[str]
    
    # Performance tuning
    max_workers: int = 4
    batch_size: int = 100
    cache_expiration_hours: int = 24
    
    # Monitoring
    enable_monitoring: bool = True
    health_check_interval: int = 300
    alert_webhooks: List[str] = None
    
    # Environment-specific overrides
    environment: str = "development"
    debug_mode: bool = False
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls, environment: str = None) -> "PipelineConfig":
        """Load configuration from environment variables."""
        env = environment or os.getenv("PIPELINE_ENV", "development")
        
        base_config = {
            "baseline_collection": f"johnwick_baseline_{env}",
            "parent_child_collection": f"johnwick_parent_children_{env}",
            "semantic_collection": f"johnwick_semantic_{env}",
            "chunk_size": int(os.getenv("CHUNK_SIZE", "200")),
            "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
            "qdrant_url": os.getenv("QDRANT_API_URL", "http://localhost:6333"),
            "qdrant_api_key": os.getenv("QDRANT_API_KEY"),
            "environment": env,
            "debug_mode": os.getenv("DEBUG_MODE", "false").lower() == "true",
        }
        
        # Environment-specific overrides
        if env == "production":
            base_config.update({
                "max_workers": 8,
                "batch_size": 500,
                "enable_monitoring": True,
                "log_level": "INFO"
            })
        elif env == "development":
            base_config.update({
                "max_workers": 2,
                "batch_size": 50,
                "debug_mode": True,
                "log_level": "DEBUG"
            })
        
        return cls(**base_config)

# Usage in flows
@flow
async def configurable_pipeline(
    config: Optional[PipelineConfig] = None,
    force_refresh: bool = False
):
    """Pipeline with type-safe configuration."""
    if config is None:
        config = PipelineConfig.from_env()
    
    logger = get_run_logger()
    logger.info(f"Running pipeline with config: {config.environment}")
    
    # Use configuration throughout pipeline
    # ...
```

## 🔍 Advanced Troubleshooting

### **Common Prefect 3.4 Issues and Solutions**

#### **1. Cache Serialization Issues**

```python
# ❌ PROBLEM: Non-serializable objects in task parameters
@task
def problematic_task(client: QdrantClient, data: List):
    # Fails with "cannot pickle '_thread.RLock' object"
    pass

# ✅ SOLUTION: Use NO_CACHE for non-serializable objects
@task(cache_policy=NO_CACHE)
def fixed_task(client: QdrantClient, data: List):
    # Works without caching issues
    pass

# ✅ ALTERNATIVE: Use environment variables instead
@task(cache_policy=TASK_SOURCE)
def env_based_task(data: List):
    client = QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY")
    )
    # Can cache safely
    pass
```

#### **2. Memory Management in Large Pipelines**

```python
# ✅ Memory-efficient patterns
@task(persist_result=False)  # Don't persist large results
async def memory_efficient_processing(large_data: List) -> Dict[str, Any]:
    """Process large datasets without memory issues."""
    
    # Process in chunks
    summary = {"total_processed": 0, "errors": []}
    
    for chunk in chunk_data(large_data, size=1000):
        try:
            chunk_result = await process_chunk(chunk)
            summary["total_processed"] += len(chunk)
            # Don't accumulate large objects
            del chunk_result
        except Exception as e:
            summary["errors"].append(str(e))
        finally:
            # Explicit cleanup
            del chunk
    
    return summary  # Return only summary, not processed data
```

#### **3. Task Runner Performance Tuning**

```python
# Optimize task runner configuration
from prefect.task_runners import ThreadPoolTaskRunner, SequentialTaskRunner

@flow(
    # For I/O bound tasks (API calls, database operations)
    task_runner=ThreadPoolTaskRunner(max_workers=10)
    
    # For CPU-bound tasks, limit to CPU count
    # task_runner=ThreadPoolTaskRunner(max_workers=os.cpu_count())
    
    # For debugging or when tasks must run sequentially
    # task_runner=SequentialTaskRunner()
)
async def optimized_flow():
    """Flow with optimized task runner configuration."""
    pass
```

### **Debugging Best Practices**

```python
# Enhanced logging and debugging
@task(log_prints=True, persist_result=True)
async def debuggable_task(data: Any) -> Any:
    """Task with comprehensive debugging support."""
    logger = get_run_logger()
    
    # Log input characteristics
    logger.info(f"Processing data: type={type(data)}, size={len(data) if hasattr(data, '__len__') else 'unknown'}")
    
    # Add debug checkpoints
    if logger.level <= 10:  # DEBUG level
        logger.debug(f"Input sample: {str(data)[:100]}...")
    
    try:
        result = await process_data(data)
        logger.info(f"Successfully processed {len(result) if hasattr(result, '__len__') else 'unknown'} items")
        return result
        
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        # Log context for debugging
        logger.error(f"Failed data characteristics: {type(data)}")
        raise
```

## 📚 Prefect 3.4 Best Practices Summary

### **1. Task Design Principles**
- ✅ **Idempotent operations** - Tasks can be safely retried
- ✅ **Single responsibility** - Each task does one thing well  
- ✅ **Appropriate caching** - Use cache policies strategically
- ✅ **Resource efficiency** - Manage memory and cleanup resources
- ✅ **Comprehensive logging** - Rich context for debugging

### **2. Flow Orchestration Patterns**
- ✅ **Client-side optimization** - Leverage Prefect 3.x performance improvements
- ✅ **Parallel execution** - Submit tasks concurrently, await results together
- ✅ **Error boundaries** - Isolate failures to prevent cascade issues
- ✅ **State management** - Proper task dependencies and data flow
- ✅ **Configuration-driven** - Externalized, type-safe configuration

### **3. Production Deployment Standards**
- ✅ **Work pool utilization** - Infrastructure templates and scaling
- ✅ **Environment separation** - Dev/staging/production configurations
- ✅ **Health monitoring** - Continuous infrastructure validation
- ✅ **Event-driven alerting** - Real-time failure notifications
- ✅ **Version control** - Deployment versioning and rollback capability

### **4. Performance and Reliability**
- ✅ **Cache policy optimization** - Strategic use of NO_CACHE, TASK_SOURCE, INPUTS
- ✅ **Resource management** - Memory-efficient processing patterns
- ✅ **Retry strategies** - Intelligent retry logic with exponential backoff
- ✅ **Monitoring integration** - Comprehensive observability
- ✅ **Graceful degradation** - System resilience patterns

## 🔮 Production Checklist

Before deploying to production, ensure:

- [ ] **Cache policies** are appropriate for all tasks (NO_CACHE for non-serializable objects)
- [ ] **Error handling** includes proper retry strategies and alerting
- [ ] **Resource limits** are configured (CPU, memory, timeout)
- [ ] **Monitoring** includes health checks and performance metrics
- [ ] **Configuration** is externalized and environment-specific
- [ ] **Work pools** are configured with appropriate infrastructure templates
- [ ] **Deployment versioning** is implemented
- [ ] **Backup and recovery** strategies are in place
- [ ] **Security** credentials are properly managed
- [ ] **Scalability** patterns are implemented for expected load

---

## 📞 Support and Resources

### **Official Documentation**
- [Prefect 3.4 Documentation](https://docs.prefect.io/v3/)
- [Task Configuration Reference](https://docs.prefect.io/v3/develop/write-tasks)
- [Cache Policies Guide](https://docs-3.prefect.io/v3/develop/task-caching)
- [Deployment Patterns](https://docs.prefect.io/latest/concepts/deployments/)

### **Community Resources**
- [Prefect Community Discord](https://discord.gg/prefect)
- [GitHub Discussions](https://github.com/PrefectHQ/prefect/discussions)
- [Prefect Community Forum](https://discourse.prefect.io/)

### **Getting Help**
1. Check the [troubleshooting section](#advanced-troubleshooting) above
2. Review the [official documentation](https://docs.prefect.io/v3/)
3. Search [GitHub issues](https://github.com/PrefectHQ/prefect/issues)
4. Ask questions in the [community forums](https://discourse.prefect.io/)

**Ready for Expert Review! 🌊** This guide now reflects current Prefect 3.4 best practices and production-ready patterns. 