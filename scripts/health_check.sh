#!/bin/bash

echo "=== Docker Compose Stack Health Check ==="

# Check if services are running
echo "Container Status:"
docker compose ps

echo -e "\n=== Service Connectivity ==="

# Test Qdrant
echo -n "Qdrant HTTP: "
curl -s http://localhost:6333 >/dev/null && echo "✅ OK" || echo "❌ FAIL"

# Test Redis
echo -n "Redis: "
docker exec langchain_redis redis-cli ping 2>/dev/null | grep -q PONG && echo "✅ OK" || echo "❌ FAIL"

# Test PostgreSQL
echo -n "PostgreSQL: "
docker exec langchain_postgres pg_isready -q && echo "✅ OK" || echo "❌ FAIL"

# Test Phoenix
echo -n "Phoenix: "
curl -s http://localhost:6006/healthz >/dev/null && echo "✅ OK" || echo "❌ FAIL"

# Test Adminer
echo -n "Adminer: "
curl -s http://localhost:8080 >/dev/null && echo "✅ OK" || echo "❌ FAIL"

echo -e "\n=== Volume Status ==="
docker volume ls | grep langchain-retrieval-methods