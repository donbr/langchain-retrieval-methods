# 🔥 Arize Phoenix Getting Started Guide

This guide walks you through setting up **Arize Phoenix** for observability in your LangChain retrieval experiments.

## 📋 Table of Contents

1. [What is Arize Phoenix?](#what-is-arize-phoenix)
2. [Installation](#installation)
3. [Docker Setup](#docker-setup)
4. [LangChain Integration](#langchain-integration)
5. [Auto-Instrumentation](#auto-instrumentation)
6. [Viewing Traces](#viewing-traces)
7. [Database Integration](#database-integration)
8. [Querying and Analysis](#querying-and-analysis)
9. [Troubleshooting](#troubleshooting)

## 🎯 What is Arize Phoenix?

**Arize Phoenix** is an open-source observability platform for AI applications that provides:

- **Automatic tracing** of LangChain components (chains, retrievers, LLMs)
- **Real-time visualization** of trace data
- **Performance monitoring** (latency, tokens, costs)
- **Error tracking** and debugging capabilities
- **OpenTelemetry standard** support for vendor neutrality

### Phoenix vs LangSmith Comparison

| Feature | Phoenix | LangSmith |
|---------|---------|-----------|
| **Setup** | Single line auto-instrumentation | Manual @traceable decorators |
| **Code overhead** | Minimal (~3 lines) | High (~200+ lines for 7 methods) |
| **Granularity** | Automatic component-level spans | Manual chain-level only |
| **Vendor lock-in** | Open source, OTEL standard | Proprietary |
| **Real-time UI** | ✅ Built-in | ❌ Limited |
| **Cost** | Free | Paid |

## 🛠️ Installation

### 1. Install Phoenix Packages

```bash
# Core Phoenix packages
pip install arize-phoenix-otel
pip install openinference-instrumentation-langchain

# Database support (for PostgreSQL backend)
pip install psycopg2-binary
pip install sqlalchemy
```

### 2. Optional: Phoenix UI (for local development)

```bash
pip install arize-phoenix
```

## 🐳 Docker Setup

Your `docker-compose.yml` already includes Phoenix with PostgreSQL backend:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: langchain_postgres
    environment:
      - POSTGRES_DB=langchain
      - POSTGRES_USER=admin
      - POSTGRES_PASSWORD=password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  phoenix:
    image: arizephoenix/phoenix:latest
    container_name: langchain_phoenix
    ports:
      - "6006:6006"  # Phoenix UI
      - "4317:4317"  # OTLP gRPC collector
    environment:
      - PHOENIX_SQL_DATABASE_URL=postgresql://admin:password@postgres:5432/phoenix
    depends_on:
      postgres:
        condition: service_healthy
```

### Start Services

```bash
# Start all services
docker compose up -d

# Check status
docker compose ps

# View Phoenix logs
docker compose logs phoenix
```

### 🤔 About the `init-db.sql` File

**Important clarification**: Let's start with **Phoenix's native capabilities** before creating custom tables!

```bash
# Minimal init-db.sql should only:
✅ Create 'phoenix' database (empty - Phoenix will populate it)
✅ Set up pgvector extension (for any future vector operations)
❌ Skip custom tables until we explore Phoenix's built-in features

# Phoenix provides out-of-the-box:
🔍 Datasets and Experiments - Native experiment management
📊 Evaluations - Built-in performance metrics
📈 Traces - Automatic observability data
🎯 Projects - Experiment organization
```

**Let's explore Phoenix's native features first:**
- **Datasets**: Organize and version your experimental data
- **Experiments**: Track and compare different retrieval methods  
- **Evaluations**: Built-in metrics and performance analysis
- **Traces**: Automatic capture of all execution details

If Phoenix's built-in capabilities don't meet our needs, we can always add custom tables later.

## 🔗 LangChain Integration

### Basic Setup (Minimal Code!)

```python
from phoenix.otel import register
from datetime import datetime

# Single line auto-instrumentation - that's it!
project_name = f"retrieval-comparison-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
tracer_provider = register(
    project_name=project_name,
    auto_instrument=True  # Automatically traces ALL LangChain components
)

print(f"✅ Phoenix auto-instrumentation enabled for: {project_name}")
```

### Environment Variables (Optional)

For Phoenix Cloud (if using hosted version):
```python
import os
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "https://app.phoenix.arize.com"
os.environ["PHOENIX_CLIENT_HEADERS"] = f"api_key={your_phoenix_api_key}"
```

For local setup (default):
```python
# Phoenix will automatically use local OTLP endpoint
# No additional configuration needed!
```

## ⚡ Auto-Instrumentation

Once Phoenix is registered, **everything is automatic**:

```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# These will be automatically traced - no decorators needed!
llm = ChatOpenAI(model="gpt-4.1-mini")
prompt = ChatPromptTemplate.from_template("Answer: {question}")

# Direct chain invocation - automatically traced!
chain = prompt | llm
result = chain.invoke({"question": "What is Phoenix?"})
```

### What Gets Traced Automatically

- **🤖 LLM calls** (OpenAI, Anthropic, etc.)
- **🔍 Retriever operations** (vector searches, BM25, etc.)
- **⛓️ Chain executions** (LCEL chains, legacy chains)
- **📊 Embeddings** (OpenAI, Cohere, etc.)
- **🏪 Vector store operations** (Qdrant, Pinecone, etc.)
- **💾 Document loaders** (CSV, PDF, etc.)

### Adding Custom Spans (Optional)

For additional context:

```python
from opentelemetry import trace

with trace.get_tracer(__name__).start_as_current_span("custom_retrieval") as span:
    span.set_attribute("method", "naive")
    span.set_attribute("question", question)
    
    result = retrieval_chain.invoke({"question": question})
    
    span.set_attribute("context_docs", len(result["context"]))
    span.set_attribute("response_length", len(result["response"].content))
```

## 👀 Viewing Traces

### 1. Access Phoenix UI

```bash
# Open in browser
open http://localhost:6006
```

### 2. Phoenix UI Features

- **📈 Real-time traces** as they're generated
- **🔍 Detailed span inspection** with timing and metadata
- **📊 Performance metrics** aggregated across runs
- **🚨 Error tracking** with full stack traces
- **📋 Trace search and filtering**

### 3. Key Views

| View | Purpose |
|------|---------|
| **Traces** | Individual execution flows |
| **Projects** | Experiment organization |
| **Spans** | Component-level details |
| **Evaluations** | Model performance metrics |

## 🗄️ Phoenix Native Capabilities

Phoenix provides comprehensive built-in features for experiment management - **let's explore these first!**

### 🔍 Phoenix Built-in Features

According to the [official Phoenix documentation](https://docs.arize.com/phoenix/), Phoenix includes:

1. **📊 Datasets**: Organize and version your experimental data natively
2. **🧪 Experiments**: Track and compare different retrieval methods  
3. **📈 Evaluations**: Built-in performance metrics and analysis
4. **🔍 Traces**: Automatic capture of all LangChain operations
5. **🎯 Projects**: Organize experiments by project

### 🏗️ Database Architecture (Phoenix-Managed)

```bash
# Phoenix automatically creates and manages:

📊 phoenix database     # Auto-created by Phoenix
   ├── spans           # ✅ Individual component executions
   ├── traces          # ✅ High-level execution flows
   ├── evaluations     # ✅ Performance metrics
   ├── datasets        # ✅ Experimental data organization
   ├── experiments     # ✅ Experiment tracking
   └── projects        # ✅ Project organization
```

### 🎯 Recommended Approach

**Phase 1: Explore Phoenix Native Features**
```python
# Use Phoenix's built-in experiment tracking
from phoenix.experimental import log_dataset, run_experiment

# Phoenix handles data organization automatically
experiment_result = run_experiment(
    name="retrieval-comparison",
    dataset=your_questions,
    model=your_retrieval_chain,
    evaluators=[accuracy, latency, cost]
)
```

**Phase 2: Custom Extensions (if needed)**
```python
# Only add custom tables if Phoenix doesn't meet our needs
# We'll evaluate this after exploring native capabilities
```

### 🔍 Verification Commands

```bash
# Check Phoenix auto-created database and tables
docker compose exec postgres psql -U admin -d phoenix -c "\dt"

# Verify Phoenix is running properly  
curl http://localhost:6006/health

# Explore Phoenix UI for native experiment features
open http://localhost:6006
```

### 🎓 Learning Phoenix Features

**Recommended exploration order:**
1. **Start experiments** and see how Phoenix tracks them automatically
2. **Use Phoenix UI** to explore datasets and evaluations features
3. **Query Phoenix tables** to understand the native data model
4. **Evaluate gaps** between Phoenix capabilities and our needs
5. **Add custom tables** only if necessary

This approach ensures we leverage Phoenix's full capabilities before building custom solutions!

## 📊 Querying and Analysis

### 1. Phoenix UI Exploration (Recommended First Step)

```bash
# Open Phoenix UI to explore native features
open http://localhost:6006

# Key areas to explore:
# - Projects: See how experiments are organized
# - Datasets: Check dataset management capabilities  
# - Evaluations: Review built-in metrics and analysis
# - Traces: Examine automatic trace capture
```

### 2. Phoenix Native API Usage

```python
import phoenix as px
from phoenix.trace import trace
from phoenix.evals import evaluate

# Phoenix's built-in experiment tracking
@trace("retrieval_experiment")
def run_retrieval_experiment(method_name, question):
    # Your retrieval logic here
    result = retrieval_chain.invoke({"question": question})
    
    # Phoenix automatically captures metrics
    return result

# Phoenix's built-in evaluation framework
evaluation_results = evaluate(
    experiment_name="retrieval-comparison",
    dataset=test_questions,
    model_function=run_retrieval_experiment,
    evaluators=[
        "hallucination",  # Built-in evaluator
        "relevance",      # Built-in evaluator
        "toxicity"        # Built-in evaluator
    ]
)
```

### 3. Query Phoenix Tables Directly (If Needed)

```python
import pandas as pd
from sqlalchemy import create_engine

# Connect to Phoenix database
phoenix_engine = create_engine("postgresql://admin:password@localhost:5432/phoenix")

# Explore Phoenix's native schema
tables_query = """
SELECT table_name, table_type 
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;
"""

tables_df = pd.read_sql(tables_query, phoenix_engine)
print("Phoenix Tables:", tables_df)

# Query spans for performance analysis
performance_query = """
SELECT 
    attributes->>'method' as method,
    AVG(EXTRACT(EPOCH FROM (end_time - start_time)) * 1000) as avg_duration_ms,
    COUNT(*) as execution_count
FROM spans 
WHERE span_name LIKE '%retrieval%'
GROUP BY attributes->>'method'
ORDER BY avg_duration_ms;
"""

performance_df = pd.read_sql(performance_query, phoenix_engine)
print(performance_df)
```

### 4. Phoenix Datasets and Experiments API

```python
# Explore Phoenix's dataset management
from phoenix.session import get_session

session = get_session()

# List available datasets
datasets = session.get_datasets()
print("Available datasets:", datasets)

# List experiments
experiments = session.get_experiments()
print("Available experiments:", experiments)

# Get detailed experiment results
for experiment in experiments:
    results = experiment.get_results()
    print(f"Experiment: {experiment.name}")
    print(f"Results: {results}")
```

### 5. Evaluation After Phoenix Exploration

```python
def assess_phoenix_capabilities():
    """
    After exploring Phoenix UI and API, evaluate:
    """
    questions_to_answer = [
        "Does Phoenix's dataset management meet our needs?",
        "Are Phoenix's built-in evaluators sufficient?", 
        "Can we track method comparisons effectively?",
        "Does the Phoenix UI provide adequate analysis?",
        "Are there any missing capabilities we need?"
    ]
    
    print("🔍 Phoenix Capabilities Assessment:")
    for question in questions_to_answer:
        print(f"   ❓ {question}")
    
    print("\n📝 Based on answers, decide if custom tables are needed")

# Run assessment after Phoenix exploration
assess_phoenix_capabilities()
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Phoenix UI Not Loading

```bash
# Check Phoenix container status
docker compose logs phoenix

# Verify ports are open
curl http://localhost:6006/health
```

#### 2. No Traces Appearing

```python
# Verify auto-instrumentation is working
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

# Check if tracer is active
print(f"Tracer: {tracer}")
print(f"Active span: {trace.get_current_span()}")
```

#### 3. Database Connection Issues

```bash
# Test PostgreSQL connection
docker compose exec postgres psql -U admin -d postgres -c "SELECT version();"

# Verify Phoenix database was auto-created
docker compose exec postgres psql -U admin -c "\l" | grep phoenix

# Check Phoenix is connecting to PostgreSQL (not SQLite)
docker compose logs phoenix | grep -i "database\|postgresql\|sqlite"

# Verify Phoenix environment variable
docker compose exec phoenix env | grep PHOENIX_SQL_DATABASE_URL
```

#### 4. Phoenix Table Creation Verification

```bash
# Phoenix should auto-create these tables:
docker compose exec postgres psql -U admin -d phoenix -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;"

# Expected output should include: spans, traces, evaluations, etc.
```

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable OpenTelemetry debug logging
import os
os.environ["OTEL_LOG_LEVEL"] = "debug"
```

### Useful Commands

```bash
# Restart Phoenix only
docker compose restart phoenix

# View all container logs
docker compose logs

# Reset everything (careful!)
docker compose down --volumes
docker compose up -d

# Check Phoenix health
curl http://localhost:6006/health
```

## 🎉 Next Steps: Phoenix-First Approach

### Phase 1: Explore Phoenix Native Capabilities

1. **🚀 Start with Phoenix UI exploration**
   ```bash
   docker compose up -d
   open http://localhost:6006
   ```

2. **🔍 Run your retrieval experiments** - Phoenix will automatically capture everything
   ```python
   # Use Phoenix's auto-instrumentation (already set up in your notebook)
   result = naive_retrieval_chain.invoke({"question": question})
   ```

3. **📊 Explore Phoenix's built-in features**:
   - **Datasets**: How does Phoenix organize experimental data?
   - **Experiments**: Can Phoenix track method comparisons effectively?  
   - **Evaluations**: Are the built-in metrics sufficient?
   - **Traces**: Is the automatic trace capture detailed enough?

4. **🧪 Test Phoenix's evaluation framework**:
   ```python
   from phoenix.evals import evaluate
   # Try Phoenix's built-in evaluators for relevance, hallucination, etc.
   ```

### Phase 2: Capability Assessment

5. **📝 Document findings**: 
   - What works well with Phoenix's native features?
   - What gaps exist for your retrieval comparison needs?
   - Which custom capabilities (if any) are truly needed?

### Phase 3: Custom Extensions (Only If Needed)

6. **🛠️ Add custom tables** only after confirming Phoenix limitations
7. **🔗 Integrate with Phoenix** rather than replacing its capabilities
8. **📈 Extend Phoenix UI** with custom visualizations if needed

### 📚 Recommended Reading Order

- [Phoenix Tracing Quickstart](https://docs.arize.com/phoenix/quickstart/phoenix-quickstart-tracing)
- [Phoenix Datasets and Experiments](https://docs.arize.com/phoenix/datasets-and-experiments/quickstart-datasets)  
- [Phoenix Evaluations](https://docs.arize.com/phoenix/quickstart/evals)

### 🤝 Community Resources

- [Phoenix Slack Community](https://arize-ai.slack.com/) - Ask about retrieval comparison best practices
- [Phoenix GitHub](https://github.com/Arize-ai/phoenix) - Check examples and tutorials
- [Phoenix Documentation](https://docs.arize.com/phoenix/) - Comprehensive guides

## 📚 Additional Resources

- [Phoenix Documentation](https://docs.arize.com/phoenix/)
- [LangChain Tracing Guide](https://docs.arize.com/phoenix/tracing/integrations-tracing/langchain)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [PostgreSQL + Phoenix](https://docs.arize.com/phoenix/deployment/self-hosting)

---

**🚀 Happy tracing!** Phoenix makes LangChain observability effortless compared to manual instrumentation approaches. 