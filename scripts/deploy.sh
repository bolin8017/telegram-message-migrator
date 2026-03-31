#!/usr/bin/env bash
# Deploy or update the app on the server
set -euo pipefail

cd "$(dirname "$0")/.."

# Check .env exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy from .env.example and fill in values:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
fi

# Check DOMAIN is set (for production with HTTPS)
if grep -q "^DOMAIN=" .env 2>/dev/null; then
    DOMAIN=$(grep "^DOMAIN=" .env | cut -d= -f2)
    echo "Deploying with domain: $DOMAIN"
else
    echo "WARNING: DOMAIN not set in .env — Caddy will serve on localhost (no HTTPS)"
fi

echo "=== Building and starting containers ==="
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

echo "=== Waiting for health check ==="
sleep 5

if docker compose ps | grep -q "(healthy)"; then
    echo "App is healthy and running!"
elif docker compose ps | grep -q "(health: starting)"; then
    echo "App is starting up (health check pending)..."
    echo "Check status with: docker compose ps"
else
    echo "WARNING: App may not be healthy. Check logs:"
    echo "  docker compose logs app"
fi

echo ""
echo "=== Useful commands ==="
echo "  docker compose logs -f app     # Follow app logs"
echo "  docker compose logs -f caddy   # Follow Caddy logs"
echo "  docker compose ps              # Check status"
echo "  docker compose down            # Stop all"
echo "  ./scripts/deploy.sh            # Redeploy (pull + rebuild)"
