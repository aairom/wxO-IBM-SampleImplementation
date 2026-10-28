#!/usr/bin/env bash
# ==============================================================================
# Master Automation Script for IBM watsonx Orchestrate Agent Architecture
#
# Usage:
#   ./scripts/automate.sh [command] [options]
#
# Commands:
#   setup     - Initialize environment, virtualenv, directories, and dependencies
#   ingest    - Ingest documentation and build local vector knowledge base
#   deploy    - Deploy tools and agents to watsonx Orchestrate instance
#   refresh   - Full end-to-end sync, re-chunk, and re-deploy pipeline
#   serve     - Launch JWT security server and local web chat interface
#   chat      - Run interactive terminal CLI chat session with local doc agent
#   status    - Check wxO connection, local vector store, and agent statuses
#   test      - Run comprehensive test suites
#   clean     - Clean temp files, logs, and build artifacts
#   help      - Display this usage help text
# ==============================================================================

set -euo pipefail

# Resolve script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/automate.log"

mkdir -p "${LOG_DIR}"

# ------------------------------------------------------------------------------
# Logging utilities
# ------------------------------------------------------------------------------
log_info() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
    echo -e "\033[1;32m${msg}\033[0m"
    echo "${msg}" >> "${LOG_FILE}"
}

log_warn() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $*"
    echo -e "\033[1;33m${msg}\033[0m"
    echo "${msg}" >> "${LOG_FILE}"
}

log_error() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*"
    echo -e "\033[1;31m${msg}\033[0m" >&2
    echo "${msg}" >> "${LOG_FILE}"
}

# ------------------------------------------------------------------------------
# Environment Setup
# ------------------------------------------------------------------------------
load_env() {
    if [[ -f "${PROJECT_ROOT}/.env" ]]; then
        log_info "Loading environment variables from .env"
        # Export all variables defined in .env
        set -a
        # shellcheck disable=SC1091
        source "${PROJECT_ROOT}/.env"
        set +a
    elif [[ -f "${PROJECT_ROOT}/.env.example" ]]; then
        log_warn ".env not found. Please copy .env.example to .env and configure credentials."
    fi
}

get_python() {
    if [[ -f "${PROJECT_ROOT}/venv/bin/python" ]]; then
        echo "${PROJECT_ROOT}/venv/bin/python"
    elif command -v uv >/dev/null 2>&1; then
        echo "uv run python"
    elif command -v python3 >/dev/null 2>&1; then
        echo "python3"
    else
        echo "python"
    fi
}

PYTHON_CMD="$(get_python)"

# ------------------------------------------------------------------------------
# Command Implementations
# ------------------------------------------------------------------------------
cmd_setup() {
    log_info "Starting project setup..."
    cd "${PROJECT_ROOT}"

    # Ensure required directories exist
    mkdir -p knowledge-bases/docs logs output scripts src/agents/ibm_doc_agent tests web

    # Virtual environment check / creation
    if [[ ! -d "venv" ]]; then
        if command -v uv >/dev/null 2>&1; then
            log_info "Creating virtual environment using uv..."
            uv venv venv
        else
            log_info "Creating virtual environment using python3 -m venv..."
            python3 -m venv venv
        fi
    fi

    # Install dependencies
    if command -v uv >/dev/null 2>&1; then
        log_info "Installing dependencies from requirements.txt using uv..."
        uv pip install -r requirements.txt --python venv/bin/python
    else
        log_info "Installing dependencies from requirements.txt using pip..."
        venv/bin/pip install -r requirements.txt
    fi

    # Ensure bash scripts have executable permissions
    chmod +x "${SCRIPT_DIR}"/*.sh 2>/dev/null || true

    log_info "Project setup completed successfully."
}

cmd_ingest() {
    load_env
    log_info "Running documentation ingestion pipeline..."
    cd "${PROJECT_ROOT}"
    ${PYTHON_CMD} scripts/ingest_docs.py "$@"
    log_info "Documentation ingestion completed."
}

cmd_deploy() {
    load_env
    log_info "Deploying agents and tools to watsonx Orchestrate instance..."
    cd "${PROJECT_ROOT}"
    ${PYTHON_CMD} scripts/deploy_orchestrate_agent.py "$@"
    log_info "Deployment completed."
}

cmd_refresh() {
    load_env
    log_info "Starting full sync and deployment pipeline..."
    cd "${PROJECT_ROOT}"
    ${PYTHON_CMD} scripts/sync_and_deploy_docs.py "$@"
    log_info "Full sync and refresh completed."
}

cmd_serve() {
    load_env
    log_info "Starting local web chat and JWT security services..."
    cd "${PROJECT_ROOT}"
    bash scripts/start.sh "$@"
}

cmd_chat() {
    load_env
    log_info "Starting interactive terminal session with IBM Doc Agent..."
    cd "${PROJECT_ROOT}"
    ${PYTHON_CMD} -m src.agents.ibm_doc_agent.agent "$@"
}

cmd_status() {
    load_env
    log_info "Checking system status and watsonx Orchestrate configuration..."
    cd "${PROJECT_ROOT}"

    echo "================================================================="
    echo "  watsonx Orchestrate System Status"
    echo "================================================================="
    echo "Project Root:      ${PROJECT_ROOT}"
    echo "Python Runtime:    $(${PYTHON_CMD} --version 2>&1 || echo 'Unavailable')"
    echo "Vector Store:      $(if [[ -f knowledge-bases/ibm_doc_store.json ]]; then echo "Present ($(grep -c '"id":' knowledge-bases/ibm_doc_store.json || echo '0') chunks)"; else echo "Missing (Run ./scripts/automate.sh ingest)"; fi)"
    echo "Source Docs:       $(find knowledge-bases/docs -type f 2>/dev/null | wc -l | tr -d ' ') files in knowledge-bases/docs/"
    echo "wxO Instance ID:   ${WO_INSTANCE_ID:-'Not set in .env'}"
    echo "wxO Environment:   ${WO_ENVIRONMENT:-'Not set in .env'}"
    echo "wxO Agent ID:      ${WO_AGENT_ID:-'Not set in .env'}"
    echo "================================================================="

    if command -v orchestrate >/dev/null 2>&1; then
        echo -e "\nRegistered Orchestrate Agents:"
        orchestrate agents list 2>&1 || log_warn "Could not list cloud agents via CLI (check auth credentials)."
    fi
}

cmd_test() {
    load_env
    log_info "Running test suites..."
    cd "${PROJECT_ROOT}"
    ${PYTHON_CMD} -m unittest discover -s tests -p "test_*.py" -v
    log_info "All test suites passed."
}

cmd_clean() {
    log_info "Cleaning up temporary files and caches..."
    cd "${PROJECT_ROOT}"
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    rm -rf .pytest_cache .coverage htmlcov 2>/dev/null || true
    log_info "Clean completed."
}

cmd_help() {
    echo "================================================================================"
    echo "  IBM watsonx Orchestrate Agent Automation CLI (automate.sh)"
    echo "================================================================================"
    echo "Usage: ./scripts/automate.sh [command] [options]"
    echo ""
    echo "Commands:"
    echo "  setup     Initialize venv, directories, permissions, and dependencies"
    echo "  ingest    Ingest source documentation and build local vector store"
    echo "  deploy    Deploy Python tools and agent definitions to watsonx Orchestrate"
    echo "  refresh   Execute full sync, re-chunking, and re-deployment pipeline"
    echo "  serve     Launch JWT authentication service and web chat interface"
    echo "  chat      Launch interactive terminal chat with local doc assistant"
    echo "  status    Show local vector store, environment variables, and agent state"
    echo "  test      Run automated unit tests for doc agent and deployment tools"
    echo "  clean     Remove bytecode cache and temporary files"
    echo "  help      Show this help documentation"
    echo "================================================================================"
}

# ------------------------------------------------------------------------------
# Main Dispatcher
# ------------------------------------------------------------------------------
main() {
    local cmd="${1:-help}"
    shift || true

    case "${cmd}" in
        setup)   cmd_setup "$@" ;;
        ingest)  cmd_ingest "$@" ;;
        deploy)  cmd_deploy "$@" ;;
        refresh) cmd_refresh "$@" ;;
        serve)   cmd_serve "$@" ;;
        chat)    cmd_chat "$@" ;;
        status)  cmd_status "$@" ;;
        test)    cmd_test "$@" ;;
        clean)   cmd_clean "$@" ;;
        help|--help|-h) cmd_help ;;
        *)
            log_error "Unknown command: ${cmd}"
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
