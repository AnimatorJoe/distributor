#!/bin/bash

# Logs Distributor Demo Script
# This script automates the demo process

set -e

echo "============================================"
echo "Logs Distributor Demo"
echo "============================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to wait for service
wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=0
    
    echo -n "Waiting for $name to be ready..."
    while [ $attempt -lt $max_attempts ]; do
        if curl -s -f "$url" > /dev/null 2>&1; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done
    
    echo -e " ${RED}✗${NC}"
    echo "Failed to connect to $name"
    return 1
}

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

echo "Step 1: Building and starting services..."
echo "----------------------------------------"
docker-compose up --build -d

echo ""
echo "Step 2: Waiting for services to be ready..."
echo "----------------------------------------"
wait_for_service "http://localhost:8000/health" "Distributor"
wait_for_service "http://localhost:8001/health" "Analyzer 1"
wait_for_service "http://localhost:8002/health" "Analyzer 2"
wait_for_service "http://localhost:8003/health" "Analyzer 3"
wait_for_service "http://localhost:8004/health" "Analyzer 4"

echo ""
echo -e "${GREEN}All services are ready!${NC}"
echo ""

echo "Step 3: Checking analyzer status..."
echo "----------------------------------------"
curl -s http://localhost:8000/analyzers | python3 -m json.tool

echo ""
echo "Step 4: Running basic load test..."
echo "----------------------------------------"
python3 load_tester/load_test.py --packets 1000 --concurrent 50

echo ""
echo "============================================"
echo "Demo Complete!"
echo "============================================"
echo ""
echo "Services are running. You can now:"
echo ""
echo "1. View distributor stats:"
echo "   curl http://localhost:8000/stats | python3 -m json.tool"
echo ""
echo "2. View individual analyzer stats:"
echo "   curl http://localhost:8001/stats | python3 -m json.tool"
echo ""
echo "3. Monitor logs:"
echo "   docker logs -f logs-distributor"
echo ""
echo "4. Test analyzer failure:"
echo "   docker stop analyzer3"
echo "   python3 load_tester/load_test.py --packets 500"
echo "   docker start analyzer3"
echo ""
echo "5. Run failure recovery test:"
echo "   python3 load_tester/load_test.py --test-failure"
echo ""
echo "6. Stop all services:"
echo "   docker-compose down"
echo ""

