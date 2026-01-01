#!/bin/bash
# CI/CD Deployment Script for Raspberry Pi
# This script is called by the GitHub Actions deploy workflow
#
# Secrets are read from /home/pi/plane-game-v4/.env.secrets (written by CI workflow)
# Required secrets in file:
#   IMAGE_TAG          - Docker image tag (commit SHA)
#   GHCR_TOKEN         - GitHub Container Registry token
#   GHCR_USER          - GitHub username for GHCR
#   FLIGHTAWARE_API_KEY - FlightAware API key (optional)
#   OPENSKY_USERNAME   - OpenSky username (optional)
#   OPENSKY_PASSWORD   - OpenSky password (optional)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

DEPLOY_DIR="/home/pi/plane-game-v4"
SECRETS_FILE="${DEPLOY_DIR}/.env.secrets"

# Load secrets from file (written by CI workflow)
if [[ -f "${SECRETS_FILE}" ]]; then
    log_info "Loading secrets from ${SECRETS_FILE}"
    # Source the secrets file (variables are not echoed)
    set -a
    source "${SECRETS_FILE}"
    set +a
    # Clean up secrets file after loading
    rm -f "${SECRETS_FILE}"
else
    log_error "Secrets file not found: ${SECRETS_FILE}"
    exit 1
fi

# Validate required environment variables
if [[ -z "${IMAGE_TAG:-}" ]]; then
    log_error "IMAGE_TAG is required"
    exit 1
fi

if [[ -z "${GHCR_TOKEN:-}" ]] || [[ -z "${GHCR_USER:-}" ]]; then
    log_error "GHCR_TOKEN and GHCR_USER are required"
    exit 1
fi

INFRA_DIR="${DEPLOY_DIR}/infra"
COMPOSE_FILE="${INFRA_DIR}/docker-compose.deploy.yml"
PI_OVERRIDE="${INFRA_DIR}/docker-compose.pi.yml"

log_info "Starting deployment of version: ${IMAGE_TAG}"

# Step 1: Log in to GitHub Container Registry
log_info "Logging into GHCR..."
echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin

# Step 2: Save current version for potential rollback
if [[ -f "${INFRA_DIR}/.current_tag" ]]; then
    PREVIOUS_TAG=$(cat "${INFRA_DIR}/.current_tag")
    echo "${PREVIOUS_TAG}" > "${INFRA_DIR}/.previous_tag"
    log_info "Saved previous version for rollback: ${PREVIOUS_TAG}"
else
    log_warn "No previous version found (first deployment)"
fi

# Step 3: Export environment variables for docker compose
export IMAGE_TAG
export FLIGHTAWARE_API_KEY="${FLIGHTAWARE_API_KEY:-}"
export OPENSKY_USERNAME="${OPENSKY_USERNAME:-}"
export OPENSKY_PASSWORD="${OPENSKY_PASSWORD:-}"

# Step 4: Pull new images
log_info "Pulling images for tag: ${IMAGE_TAG}"
cd "${INFRA_DIR}"
docker compose -f "${COMPOSE_FILE}" pull

# Step 5: Stop existing containers gracefully
log_info "Stopping existing containers..."
docker compose -f "${COMPOSE_FILE}" -f "${PI_OVERRIDE}" down --timeout 30 || true

# Step 6: Start new containers
log_info "Starting new containers..."
docker compose -f "${COMPOSE_FILE}" -f "${PI_OVERRIDE}" up -d

# Step 7: Wait for services to start
log_info "Waiting for services to start..."
sleep 10

# Step 8: Health check
log_info "Running health checks..."
HEALTH_CHECK_PASSED=false

for i in {1..12}; do
    log_info "Health check attempt ${i}/12..."

    if curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
        log_info "Backend health check passed!"
        HEALTH_CHECK_PASSED=true
        break
    fi

    sleep 5
done

if [[ "${HEALTH_CHECK_PASSED}" == "true" ]]; then
    # Save current version
    echo "${IMAGE_TAG}" > "${INFRA_DIR}/.current_tag"
    log_info "Deployment successful! Version ${IMAGE_TAG} is now live."

    # Clean up old images to save disk space
    log_info "Cleaning up old images..."
    docker image prune -f --filter "until=24h" || true

    exit 0
else
    log_error "Health check failed after 60 seconds"

    # Attempt automatic rollback
    if [[ -f "${INFRA_DIR}/.previous_tag" ]]; then
        PREVIOUS_TAG=$(cat "${INFRA_DIR}/.previous_tag")
        log_warn "Attempting rollback to ${PREVIOUS_TAG}..."

        export IMAGE_TAG="${PREVIOUS_TAG}"
        docker compose -f "${COMPOSE_FILE}" -f "${PI_OVERRIDE}" up -d

        sleep 10

        if curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
            echo "${PREVIOUS_TAG}" > "${INFRA_DIR}/.current_tag"
            log_warn "Rollback successful. Running version: ${PREVIOUS_TAG}"
        else
            log_error "Rollback also failed! Manual intervention required."
        fi
    else
        log_error "No previous version available for rollback"
    fi

    exit 1
fi
