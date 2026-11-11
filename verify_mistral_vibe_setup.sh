#!/bin/bash

# Mistral Vibe Setup Verification Script
# Run this to verify all components are properly configured

set -e

echo "=========================================="
echo "Mistral Vibe Setup Verification"
echo "=========================================="
echo ""

SWARM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SWARM_ROOT"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0

check() {
    local name="$1"
    local command="$2"
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $name"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} $name"
        ((FAILED++))
        return 1
    fi
}

check_file() {
    local name="$1"
    local file="$2"
    
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $name"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} $name"
        echo "  Missing file: $file"
        ((FAILED++))
        return 1
    fi
}

check_content() {
    local name="$1"
    local file="$2"
    local pattern="$3"
    
    if [ -f "$file" ] && grep -q "$pattern" "$file"; then
        echo -e "${GREEN}✓${NC} $name"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} $name"
        echo "  File: $file"
        echo "  Pattern not found: $pattern"
        ((FAILED++))
        return 1
    fi
}

echo "Checking frontend files..."
echo "----------------------------------------"

check_file "chat.js exists" "frontend/static/js/views/chat.js"
check_content "Mistral Vibe in participants" "frontend/static/js/views/chat.js" "mistral-vibe"
check_content "Tiered Assistant in participants" "frontend/static/js/views/chat.js" "tiered-assistant"
check_content "Mistral Vibe in aliases" "frontend/static/js/views/chat.js" "'mistral-vibe': 'mistral-vibe'"
check_content "Tiered Assistant in aliases" "frontend/static/js/views/chat.js" "'tiered-assistant': 'tiered-assistant'"
check_content "Mistral Vibe in dispatch regex" "frontend/static/js/views/chat.js" "mistral(-vibe)?"
check_content "Tiered Assistant in dispatch regex" "frontend/static/js/views/chat.js" "tiered(-assistant)?"

echo ""
echo "Checking backend files..."
echo "----------------------------------------"

check_file "Mistral Vibe agent" "core/mistral_vibe_agent.py"
check_file "Tiered assistant" "core/apex_tiered_assistant.py"
check_file "Service accounts" "core/service_accounts.py"
check_file "Peer bridge" "core/peer_bridge.py"

check_content "Mistral Vibe in service accounts" "core/service_accounts.py" "('mistral-vibe', 'Mistral Vibe')"
check_content "Tiered Assistant in service accounts" "core/service_accounts.py" "('tiered-assistant', 'Tiered Model Assistant')"
check_content "Mistral Vibe in peer bridge MENTIONS" "core/peer_bridge.py" "'mistral-vibe': 'mistral-vibe'"
check_content "Tiered Assistant in peer bridge MENTIONS" "core/peer_bridge.py" "'tiered-assistant': 'tiered-assistant'"
check_content "Mistral Vibe in peer bridge SCOPES" "core/peer_bridge.py" "'mistral-vibe':"
check_content "Tiered Assistant in peer bridge SCOPES" "core/peer_bridge.py" "'tiered-assistant':"

check_content "Mistral Vibe in agent seed" "utils/db/_schema.py" "'mistral-vibe'"

echo ""
echo "Checking configuration scripts..."
echo "----------------------------------------"

check_file "Mistral Vibe config" "ops/mistral_vibe_config.py"
check_file "Tiered config" "ops/apex_tiered_config.py"
check_file "SQL script" "ops/add_mistral_vibe_to_ui.sql"

echo ""
echo "Checking documentation..."
echo "----------------------------------------"

check_file "FINAL_SETUP_GUIDE.md" "FINAL_SETUP_GUIDE.md"
check_file "MISTRAL_VIBE_UI_INTEGRATION.md" "MISTRAL_VIBE_UI_INTEGRATION.md"
check_file "MISTRAL_VIBE_INTEGRATION.md" "MISTRAL_VIBE_INTEGRATION.md"
check_file "APEX_TIERED_FALLBACK.md" "ops/APEX_TIERED_FALLBACK.md"

echo ""
echo "Checking test files..."
echo "----------------------------------------"

check_file "Tiered tests" "tests/test_apex_tiered_assistant.py"
check_file "Mistral tests" "tests/test_mistral_vibe_integration.py"

echo ""
echo "Checking environment..."
echo "----------------------------------------"

if [ -n "$MISTRAL_API_KEY" ]; then
    echo -e "${GREEN}✓${NC} MISTRAL_API_KEY is set"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠${NC} MISTRAL_API_KEY is not set (will need it for API calls)"
    echo "  Run: export MISTRAL_API_KEY=your_key"
    ((FAILED++))
fi

echo ""
echo "Checking database..."
echo "----------------------------------------"

if [ -f "swarm_hive.db" ]; then
    check_content "Mistral Vibe in database" "swarm_hive.db" "mistral-vibe"
    check_content "Tiered Assistant in database" "swarm_hive.db" "tiered-assistant"
else
    echo -e "${YELLOW}⚠${NC} swarm_hive.db not found"
    echo "  Run: sqlite3 swarm_hive.db < ops/add_mistral_vibe_to_ui.sql"
fi

echo ""
echo "Checking llm_registry.yaml..."
echo "----------------------------------------"

if [ -f "ops/llm_registry.yaml" ]; then
    check_content "Mistral model in registry" "ops/llm_registry.yaml" "mistral"
else
    echo -e "${YELLOW}⚠${NC} ops/llm_registry.yaml not found or not readable"
fi

echo ""
echo "=========================================="
echo "Results"
echo "=========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    echo "Mistral Vibe is ready to use!"
    echo ""
    echo "To use:"
    echo "  1. Set API key: export MISTRAL_API_KEY=your_key"
    echo "  2. Run SQL: sqlite3 swarm_hive.db < ops/add_mistral_vibe_to_ui.sql"
    echo "  3. Open UI: http://127.0.0.1:5050/ui"
    echo "  4. Dispatch: [DISPATCH: @mistral-vibe] Your message"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some checks failed${NC}"
    echo ""
    echo "Review the failed checks above and follow the instructions."
    echo ""
    exit 1
fi
