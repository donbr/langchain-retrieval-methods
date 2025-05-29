# Docker Admin Guide for LangChain Retrieval Methods

## Overview

This guide provides essential Docker administration commands for managing the infrastructure supporting your LangChain Retrieval Methods notebook. The stack includes Qdrant (vector database), Redis (key-value store), PostgreSQL (relational database), Phoenix (AI observability), and Adminer (database management).

## Quick Reference

### ☕ Daily Operations
| Action | Command | Purpose |
|--------|---------|---------|
| **Morning Coffee Startup** | `docker compose up -d` | Start all services in background |
| **Check Service Status** | `docker compose ps` | View running containers |
| **View All Logs** | `docker compose logs -f` | Follow logs from all services |
| **That's a Wrap** | `docker compose down` | Stop all services, keep data |
| **🔥 Burn It All Down** | `docker compose down --volumes --rmi all` | Complete reset + cleanup |

## Service Management

### Starting Services

**Basic Startup:**
```bash
# Start all services in detached mode
docker compose up -d

# Start specific services only
docker compose up -d qdrant redis postgres
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
```

**Backup Data:**
```bash
# Backup Qdrant data
docker run --rm -v langchain-retrieval-methods_qdrant_data:/data -v $(pwd):/backup alpine tar czf /backup/qdrant_backup.tar.gz /data

# Backup PostgreSQL data
docker run --rm -v langchain-retrieval-methods_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data

# Backup Redis data
docker run --rm -v langchain-retrieval-methods_redis_data:/data -v $(pwd):/backup alpine tar czf /backup/redis_backup.tar.gz /data
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

### PostgreSQL Database

**Connection Information:**
- **Port**: 5432
- **Username**: From `POSTGRES_USER` env var (default: postgres)
- **Password**: From `POSTGRES_PASSWORD` env var
- **Database**: From `POSTGRES_DB` env var (default: langchain_db)

**Database Operations:**
```bash
# Connect to PostgreSQL
docker exec -it langchain_postgres psql -U postgres -d langchain_db

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
docker exec langchain_postgres pg_dump -U postgres langchain_db > backup.sql

# Restore from backup
docker exec -i langchain_postgres psql -U postgres langchain_db < backup.sql
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
docker compose restart qdrant phoenix
```

**Permission Errors:**
```bash
# Fix volume permissions (Linux/macOS)
sudo chown -R 1000:1000 $(docker volume inspect langchain-retrieval-methods_qdrant_data --format '{{.Mountpoint}}')
```

**Service Won't Start:**
```bash
# Check detailed error logs
docker compose logs service_name

# Remove and recreate problematic container
docker compose rm -f service_name
docker compose up -d service_name
```

### Health Verification

**Complete Stack Health Check:**
```bash
bash scripts/health_check.sh
```

## Environment Configuration

### Environment Variables

Create a `.env` file in your project directory:
```bash
# PostgreSQL Configuration
POSTGRES_USER=langchain_user
POSTGRES_PASSWORD=secure_password_123
POSTGRES_DB=langchain_database

# Qdrant Configuration (if using Qdrant Cloud)
QDRANT_API_KEY=your_qdrant_api_key
QDRANT_API_URL=https://your-cluster.qdrant.tech

# Optional: Customize Adminer
ADMINER_DESIGN=nette
```

### Security Considerations

**Production Checklist:**
- [ ] Change default passwords
- [ ] Use Docker secrets instead of environment variables
- [ ] Enable SSL/TLS for external connections
- [ ] Restrict network access with custom networks
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

# PostgreSQL connection
DATABASE_URL = "postgresql://langchain_user:password@localhost:5432/langchain_database"

# Phoenix tracing
PHOENIX_COLLECTOR_ENDPOINT = "http://localhost:6006"
```

### Service Dependencies

Based on your notebook code, ensure this startup order:
1. **Redis** (for parent document storage)
2. **Qdrant** (for vector storage)
3. **PostgreSQL** (for structured data)
4. **Phoenix** (depends on other services for tracing)
5. **Adminer** (depends on PostgreSQL)

## References

- **Docker Compose Documentation**: https://docs.docker.com/compose/
- **Qdrant Documentation**: https://qdrant.tech/documentation/
- **Redis Documentation**: https://redis.io/documentation
- **PostgreSQL Docker**: https://hub.docker.com/_/postgres
- **Phoenix Documentation**: https://docs.arize.com/phoenix
- **Adminer Documentation**: https://www.adminer.org/

---

*This guide is optimized for the LangChain Retrieval Methods notebook environment as of May 2025.*