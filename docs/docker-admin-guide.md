# Docker Admin Guide for LangChain Retrieval Methods

## Overview

This guide provides essential Docker administration commands for managing the infrastructure supporting your LangChain Retrieval Methods notebook. The stack includes Qdrant (vector database), Redis (key-value store), PostgreSQL (relational database), Phoenix (AI observability), Adminer (database management), MinIO (object storage), and Prefect (workflow orchestration).

## Quick Reference

### ☕ Daily Operations
| Action | Command | Purpose |
|--------|---------|---------|
| **Morning Coffee Startup** | `docker compose up -d` | Start all services in background |
| **Check Service Status** | `docker compose ps` | View running containers |
| **View All Logs** | `docker compose logs -f` | Follow logs from all services |
| **Check Prefect Workflows** | `docker compose logs -f prefect-server` | Monitor workflow orchestration |
| **That's a Wrap** | `docker compose down` | Stop all services, keep data |
| **🔥 Burn It All Down** | `docker compose down --volumes --rmi all` | Complete reset + cleanup |

### User Interfaces

| Service | URL | Credentials | Purpose |
|---------|-----|-------------|---------|
| **Qdrant Dashboard** | http://localhost:6333/dashboard | None (or API key if configured) | Vector database management & collection browser |
| **MinIO Console** | http://localhost:9001 | Username: `minioadmin`<br>Password: `minioadmin123` | Object storage management & bucket operations |
| **Prefect UI** | http://localhost:4200 | None (default) | Workflow orchestration, runs & deployment monitoring |
| **Phoenix UI** | http://localhost:6006 | None | AI observability, traces & span analysis |
| **Adminer** | http://localhost:8080 | see below | Database management & SQL queries |
| **RedisInsight** | http://localhost:5540 | None (default) | Redis GUI for browsing, querying, and visualizing Redis data |

#### Adminer - Arize Phoenix and General Use
- **Server**: `postgres`
- **Username**: `langchain_user`
- **Password**: `secure_password_123`
- **Database**: `langchain_database`

#### Adminer - Prefect Postgres Database:
- **Server**: `prefect-postgres`
- **Username**: `prefect` 
- **Password**: `prefect`
- **Database**: `prefect_server`

### RedisInsight (GUI for Redis)

**Connection Information:**
- **URL:** http://localhost:5540
- **Port:** 5540
- **Password:** None (default configuration)

**Usage:**
- Open your browser and go to http://localhost:5540
- Add a new Redis database connection:
  - **Host:** `redis`
  - **Port:** `6379`
  - **Password:** (leave blank unless you set one)
- Browse keys, run queries, visualize data, and monitor Redis performance.

**Troubleshooting:**
```bash
# Check RedisInsight logs
docker compose logs -f redisinsight

# Restart RedisInsight service
docker compose restart redisinsight

# Remove and recreate RedisInsight container (data is persisted in volume)
docker compose rm -f redisinsight
docker compose up -d redisinsight
```

**References:**
- [RedisInsight Docker Hub](https://hub.docker.com/r/redis/redisinsight)
- [RedisInsight Documentation](https://docs.redis.com/latest/ri/)

## Service Management

### Starting Services

**Basic Startup:**
```bash
# Start all services in detached mode
docker compose up -d

# Start specific services only
docker compose up -d qdrant redis postgres

# Start workflow orchestration stack
docker compose up -d prefect-postgres prefect-server

# Start storage services
docker compose up -d minio postgres redis
```

**With Rebuild:**
```bash
# Force rebuild if you've modified configurations
docker compose up -d --build
```

### Monitoring Services

**Service Status:**
```bash
# Check which containers are running
docker compose ps

# Extended information with resource usage
docker stats
```

**Log Management:**
```bash
# View logs from all services
docker compose logs -f

# View logs from specific service
docker compose logs -f qdrant
docker compose logs -f redis
docker compose logs -f postgres
docker compose logs -f phoenix
docker compose logs -f adminer
docker compose logs -f minio
docker compose logs -f prefect-postgres
docker compose logs -f prefect-server

# View last 100 lines only
docker compose logs --tail=100 qdrant
```

### Service Control

**Individual Service Management:**
```bash
# Restart specific service
docker compose restart qdrant
docker compose restart redis
docker compose restart postgres
docker compose restart minio
docker compose restart prefect-server

# Stop specific service
docker compose stop phoenix

# Start stopped service
docker compose start phoenix
```

## Data Management

### Volume Operations

**List Volumes:**
```bash
# List all Docker volumes
docker volume ls

# Inspect specific volume
docker volume inspect langchain-retrieval-methods_phoenix_data
docker volume inspect langchain-retrieval-methods_postgres_data
docker volume inspect langchain-retrieval-methods_qdrant_data
docker volume inspect langchain-retrieval-methods_redis_data
docker volume inspect langchain-retrieval-methods_minio_data
docker volume inspect langchain-retrieval-methods_prefect_postgres_data
```

**Backup Data:**
```bash
# Backup Qdrant data
docker run --rm -v langchain-retrieval-methods_qdrant_data:/data -v $(pwd):/backup alpine tar czf /backup/qdrant_backup.tar.gz /data

# Backup PostgreSQL data
docker run --rm -v langchain-retrieval-methods_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data

# Backup Redis data
docker run --rm -v langchain-retrieval-methods_redis_data:/data -v $(pwd):/backup alpine tar czf /backup/redis_backup.tar.gz /data

# Backup MinIO data
docker run --rm -v langchain-retrieval-methods_minio_data:/data -v $(pwd):/backup alpine tar czf /backup/minio_backup.tar.gz /data

# Backup Prefect database
docker run --rm -v langchain-retrieval-methods_prefect_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/prefect_backup.tar.gz /data
```

### Data Reset Operations

**⚠️ WARNING: These operations will DELETE ALL DATA**

**Reset Individual Services:**
```bash
# Stop service and remove its volume
docker compose stop qdrant
docker volume rm langchain-retrieval-methods_qdrant_data
docker compose up -d qdrant

# Reset Redis data
docker compose stop redis
docker volume rm langchain-retrieval-methods_redis_data
docker compose up -d redis

# Reset MinIO buckets and objects
docker compose stop minio
docker volume rm langchain-retrieval-methods_minio_data
docker compose up -d minio

# Reset Prefect workflows and runs
docker compose stop prefect-server prefect-postgres
docker volume rm langchain-retrieval-methods_prefect_postgres_data
docker compose up -d prefect-postgres prefect-server
```

**Complete Stack Reset:**
```bash
# Nuclear option - removes everything
docker compose down --volumes --rmi all
docker compose up -d
```

## Service-Specific Administration

### Qdrant Vector Database

**Connection Information:**
- **HTTP API**: http://localhost:6333
- **gRPC API**: localhost:6334
- **Dashboard**: http://localhost:6333/dashboard

**Health Checks:**
```bash
# Test Qdrant API connectivity
curl http://localhost:6333

# Check collection status (requires API key if configured)
curl http://localhost:6333/collections
```

**Collection Management:**
```bash
# Access Qdrant container for direct management
docker exec -it langchain_qdrant /bin/sh

# View collection information via API
curl http://localhost:6333/collections/johnwick_baseline
curl http://localhost:6333/collections/johnwick_parent_children
curl http://localhost:6333/collections/johnwick_semantic
```

### Redis Key-Value Store

**Connection Information:**
- **Port**: 6379
- **Password**: None (default configuration)

**Data Operations:**
```bash
# Connect to Redis CLI
docker exec -it langchain_redis redis-cli

# Basic Redis commands inside container
# Check connection
PING

# List all keys
KEYS *

# Get key information
TYPE parent_document_store:some_key_id

# Memory usage
INFO memory

# Exit Redis CLI
exit
```

**Monitoring:**
```bash
# Monitor Redis operations in real-time
docker exec -it langchain_redis redis-cli MONITOR
```

### RedisInsight (GUI for Redis)

**Connection Information:**
- **URL:** http://localhost:5540
- **Port:** 5540
- **Password:** None (default configuration)

**Usage:**
- Open your browser and go to http://localhost:5540
- Add a new Redis database connection:
  - **Host:** `redis`
  - **Port:** `6379`
  - **Password:** (leave blank unless you set one)
- Browse keys, run queries, visualize data, and monitor Redis performance.

**Troubleshooting:**
```bash
# Check RedisInsight logs
docker compose logs -f redisinsight

# Restart RedisInsight service
docker compose restart redisinsight

# Remove and recreate RedisInsight container (data is persisted in volume)
docker compose rm -f redisinsight
docker compose up -d redisinsight
```

**References:**
- [RedisInsight Docker Hub](https://hub.docker.com/r/redis/redisinsight)
- [RedisInsight Documentation](https://docs.redis.com/latest/ri/)

### PostgreSQL Database (Main)

**Connection Information:**
- **Port**: 5432
- **Username**: From `POSTGRES_USER` env var (default: langchain_user)
- **Password**: From `POSTGRES_PASSWORD` env var
- **Database**: From `POSTGRES_DB` env var (default: langchain_database)

**Database Operations:**
```bash
# Connect to PostgreSQL
docker exec -it langchain_postgres psql -U langchain_user -d langchain_database

# Common PostgreSQL commands inside container:
# List databases
\l

# List tables
\dt

# Exit PostgreSQL
\q
```

**Backup and Restore:**
```bash
# Create database backup
docker exec langchain_postgres pg_dump -U langchain_user langchain_database > backup.sql

# Restore from backup
docker exec -i langchain_postgres psql -U langchain_user langchain_database < backup.sql
```

### MinIO Object Storage

**Connection Information:**
- **API Port**: 9000
- **Console Port**: 9001
- **Console URL**: http://localhost:9001
- **API URL**: http://localhost:9000
- **Default Username**: minioadmin (configurable via `MINIO_ROOT_USER`)
- **Default Password**: minioadmin123 (configurable via `MINIO_ROOT_PASSWORD`)

**Web Console Operations:**
```bash
# Access MinIO web console
# Navigate to http://localhost:9001
# Login with MINIO_ROOT_USER and MINIO_ROOT_PASSWORD
```

**CLI Operations:**
```bash
# Install MinIO client (mc) if not already installed
docker exec -it langchain_minio /bin/sh

# Inside container, configure alias
mc alias set local http://localhost:9000 minioadmin minioadmin123

# Create bucket
mc mb local/langchain-documents

# List buckets
mc ls local

# Upload file
mc cp /path/to/file local/langchain-documents/

# List objects in bucket
mc ls local/langchain-documents

# Download file
mc cp local/langchain-documents/file.txt ./
```

**Bucket Management:**
```bash
# Check bucket usage
docker exec langchain_minio mc du local/langchain-documents

# Set bucket policy (for public access)
docker exec langchain_minio mc policy set public local/langchain-documents

# Remove bucket (WARNING: Deletes all objects)
docker exec langchain_minio mc rb local/langchain-documents --force
```

### Prefect Workflow Orchestration

**Connection Information:**
- **Prefect UI**: http://localhost:4200
- **Prefect Database Port**: 5433 (dedicated PostgreSQL instance)
- **Database User**: prefect
- **Database Password**: prefect
- **Database Name**: prefect_server

**Prefect Server Management:**
```bash
# Check Prefect server status
curl http://localhost:4200/api/health

# View Prefect logs
docker compose logs -f prefect-server

# Restart Prefect server
docker compose restart prefect-server
```

**Database Operations (Prefect-specific):**
```bash
# Connect to Prefect PostgreSQL database
docker exec -it prefect-postgres psql -U prefect -d prefect_server

# List tables (inside psql)
\dt

# Check active flows
SELECT name, created FROM flow ORDER BY created DESC LIMIT 10;

# Exit PostgreSQL
\q
```

**Workflow Management:**
```bash
# Access Prefect server container
docker exec -it prefect-server /bin/bash

# Inside container, use Prefect CLI
prefect flow ls
prefect deployment ls
prefect work-queue ls

# Check server configuration
prefect config view
```

### Phoenix AI Observability

**Access Information:**
- **Web UI**: http://localhost:6006
- **gRPC OTLP**: localhost:4317

**Log Analysis:**
```bash
# Monitor Phoenix traces and spans
docker compose logs -f phoenix

# Check Phoenix health
curl http://localhost:6006/healthz
```

### Adminer Database Management

**Access Information:**
- **Web Interface**: http://localhost:8080
- **Pre-configured Server**: postgres (container name)

**Login Credentials:**
- **Server**: postgres
- **Username**: Value of `POSTGRES_USER`
- **Password**: Value of `POSTGRES_PASSWORD`
- **Database**: Value of `POSTGRES_DB`

**Multiple Database Access:**
For Prefect database access via Adminer:
- **Server**: prefect-postgres
- **Username**: prefect
- **Password**: prefect
- **Database**: prefect_server

## Troubleshooting

### Common Issues

**Port Conflicts:**
```bash
# Check what's using a port
netstat -tulpn | grep :6333
lsof -i :6333

# If port is occupied, modify docker-compose.yml:
ports:
  - "16333:6333"  # Use different host port
```

**Memory Issues:**
```bash
# Check Docker resource usage
docker stats

# Restart memory-intensive services
docker compose restart qdrant phoenix prefect-server
```

**Permission Errors:**
```bash
# Fix volume permissions (Linux/macOS)
sudo chown -R 1000:1000 $(docker volume inspect langchain-retrieval-methods_qdrant_data --format '{{.Mountpoint}}')
sudo chown -R 999:999 $(docker volume inspect langchain-retrieval-methods_minio_data --format '{{.Mountpoint}}')
```

**Service Won't Start:**
```bash
# Check detailed error logs
docker compose logs service_name

# Remove and recreate problematic container
docker compose rm -f service_name
docker compose up -d service_name
```

**MinIO Access Issues:**
```bash
# Reset MinIO credentials
docker compose down minio
docker volume rm langchain-retrieval-methods_minio_data
docker compose up -d minio

# Check MinIO logs for authentication errors
docker compose logs minio
```

**Prefect Server Issues:**
```bash
# Reset Prefect database connection
docker compose restart prefect-postgres prefect-server

# Check database connectivity
docker exec prefect-server prefect config view

# Reinitialize Prefect database
docker compose down prefect-server prefect-postgres
docker volume rm langchain-retrieval-methods_prefect_postgres_data
docker compose up -d prefect-postgres prefect-server
```

### Health Verification

**Complete Stack Health Check:**
```bash
bash scripts/health_check.sh
```

**Individual Service Health:**
```bash
# Qdrant
curl -f http://localhost:6333 || echo "Qdrant not healthy"

# Redis
docker exec langchain_redis redis-cli ping || echo "Redis not healthy"

# PostgreSQL (main)
docker exec langchain_postgres pg_isready -U langchain_user || echo "PostgreSQL not healthy"

# MinIO
curl -f http://localhost:9001 || echo "MinIO not healthy"

# Prefect
curl -f http://localhost:4200/api/health || echo "Prefect not healthy"

# Phoenix
curl -f http://localhost:6006/healthz || echo "Phoenix not healthy"
```

## Environment Configuration

### Environment Variables

Create a `.env` file in your project directory:
```bash
# === API Keys (if used in your app code) ===
OPENAI_API_KEY=your-openai-api-key-here
COHERE_API_KEY=your-cohere-api-key-here

# === Qdrant Configuration ===
QDRANT_API_KEY=your-qdrant-api-key-here
QDRANT_API_URL=your-qdrant-api-url-here
QDRANT__LOG_LEVEL=INFO

# === LangSmith Configuration === (optional, if using LangSmith)
LANGSMITH_API_KEY=your-langsmith-api-key-here

# === PostgreSQL Configuration (Main Database) ===
POSTGRES_USER=langchain_user
POSTGRES_PASSWORD=secure_password_123  # Change this for production!
POSTGRES_DB=langchain_database

# === Prefect PostgreSQL Configuration (Dedicated Prefect Database) ===
PREFECT_POSTGRES_USER=prefect
PREFECT_POSTGRES_PASSWORD=prefect_secure_password_456  # Change this for production!
PREFECT_POSTGRES_DB=prefect

# === Adminer UI Theme (optional) ===
ADMINER_DESIGN=nette
# ADMINER_DESIGN=pepa-linha-dark

# === MinIO Storage Configuration ===
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123  # Change this for production!

# === Phoenix AI Observability ===
PHOENIX_COLLECTOR_ENDPOINT=http://127.0.0.1:6006
PHOENIX_SQL_DATABASE_URL=postgresql://langchain_user:secure_password_123@postgres:5432/langchain_database

# === Prefect Database URLs ===
# For Alembic Migrations (this must be +asyncpg)
PREFECT_SERVER_DATABASE_URL=postgresql+asyncpg://langchain_user:secure_password_123@postgres:5432/langchain_database

# For the "Service" layer and "API" layer—also +asyncpg
PREFECT_SERVER_DATABASE_CONNECTION_URL=postgresql+asyncpg://langchain_user:secure_password_123@postgres:5432/langchain_database
PREFECT_API_DATABASE_URL=postgresql+asyncpg://langchain_user:secure_password_123@postgres:5432/langchain_database
PREFECT_API_DATABASE_CONNECTION_URL=postgresql+asyncpg://langchain_user:secure_password_123@postgres:5432/langchain_database
```

### Security Considerations

**Production Checklist:**
- [ ] Change default passwords for all services
- [ ] Use Docker secrets instead of environment variables
- [ ] Enable SSL/TLS for external connections
- [ ] Restrict network access with custom networks
- [ ] Configure MinIO with proper access policies
- [ ] Set up Prefect authentication and authorization
- [ ] Regular security updates: `docker compose pull && docker compose up -d`

## Performance Optimization

### Resource Limits

Add resource constraints to your docker-compose.yml:
```yaml
services:
  qdrant:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
        reservations:
          memory: 2G

  postgres:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'

  minio:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'

  prefect-server:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
```

### Monitoring Commands

```bash
# Monitor resource usage
watch docker stats

# Check disk usage by service
docker system df

# Clean up unused images and containers
docker system prune -f
```

## Integration with Notebook

### Service URLs for Your Code

Your notebook should use these connection strings:

```python
# Qdrant connection
QDRANT_URL = "http://localhost:6333"  # or your cloud URL

# Redis connection  
REDIS_URL = "redis://localhost:6379"

# PostgreSQL connection (main database)
DATABASE_URL = "postgresql://langchain_user:password@localhost:5432/langchain_database"

# MinIO S3-compatible storage
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"  # or your configured value
MINIO_SECRET_KEY = "minioadmin123"  # or your configured value
MINIO_BUCKET = "langchain-documents"

# Prefect configuration
PREFECT_API_URL = "http://localhost:4200/api"

# Phoenix tracing
PHOENIX_COLLECTOR_ENDPOINT = "http://localhost:6006"
```

### Service Dependencies

Based on your docker-compose.yml, ensure this startup order:
1. **PostgreSQL** (main database - foundation for other services)
2. **Prefect-PostgreSQL** (dedicated workflow database)
3. **Redis** (for parent document storage and caching)
4. **MinIO** (for object storage)
5. **Qdrant** (for vector storage)
6. **Prefect Server** (depends on prefect-postgres)
7. **Phoenix** (depends on PostgreSQL for trace storage)
8. **Adminer** (depends on PostgreSQL for management)

### Common Integration Patterns

**Document Storage Workflow:**
```python
# Store documents in MinIO
# Create embeddings and store in Qdrant
# Cache metadata in Redis
# Track processing in Phoenix
# Orchestrate with Prefect workflows
```

**LangChain + MinIO Integration:**
```python
from langchain.document_loaders import S3FileLoader
from langchain.vectorstores import Qdrant

# Configure MinIO as S3-compatible storage
s3_loader = S3FileLoader(
    bucket="langchain-documents",
    key="document.pdf",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin123"
)
```

## References

- **Docker Compose Documentation**: https://docs.docker.com/compose/
- **Qdrant Documentation**: https://qdrant.tech/documentation/
- **Redis Documentation**: https://redis.io/documentation
- **PostgreSQL Docker**: https://hub.docker.com/_/postgres
- **Phoenix Documentation**: https://docs.arize.com/phoenix
- **Adminer Documentation**: https://www.adminer.org/
- **MinIO Documentation**: https://min.io/docs/minio/linux/index.html
- **Prefect Documentation**: https://docs.prefect.io/

---

*This guide is optimized for the LangChain Retrieval Methods notebook environment as of May 2025.*