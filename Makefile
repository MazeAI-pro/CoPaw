# Makefile for CoPaw Docker Deployment
# Usage: make <command> [VARIABLE=VALUE ...]
#
# Variables:
#   IMAGE      - Docker image name (default: copaw-auth)
#   CONTAINER  - Container name (default: copaw)
#   PORT       - Host port mapping (default: 8088)
#   VOLUME     - Data volume name (default: copaw-data)
#   DOCKERFILE - Dockerfile path (default: deploy/Dockerfile.auth)

IMAGE      ?= copaw-auth
CONTAINER  ?= copaw
PORT       ?= 8088
VOLUME     ?= copaw-data
DOCKERFILE ?= deploy/Dockerfile.auth

.PHONY: build run stop restart logs ps shell clean update help

# Default target
.DEFAULT_GOAL := help

## ----------------------------------------------------------------------------
## Docker Commands
## ----------------------------------------------------------------------------

## build: Build Docker image
build:
	@echo "Building image: $(IMAGE)"
	docker build -t $(IMAGE) -f $(DOCKERFILE) .
	@echo "Build complete: $(IMAGE)"

## run: Start container in detached mode
run:
	@echo "Starting container: $(CONTAINER)"
	docker run -d \
		--name $(CONTAINER) \
		-p $(PORT):8088 \
		-v $(VOLUME):/app/working \
		$(IMAGE)
	@echo "Container started on port $(PORT)"
	@echo "View logs: make logs"

## stop: Stop and remove container
stop:
	@echo "Stopping container: $(CONTAINER)"
	-docker stop $(CONTAINER) 2>/dev/null || true
	-docker rm $(CONTAINER) 2>/dev/null || true
	@echo "Container stopped and removed"

## restart: Stop and start container (rebuild not included)
restart: stop run

## logs: View container logs (follow mode)
logs:
	docker logs -f $(CONTAINER)

## ps: Show container status
ps:
	@docker ps -a --filter "name=$(CONTAINER)" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

## shell: Open bash shell in container
shell:
	docker exec -it $(CONTAINER) /bin/bash

## clean: Remove container, image, and data volume
clean: stop
	@echo "Removing image: $(IMAGE)"
	-docker rmi $(IMAGE) 2>/dev/null || true
	@echo "Removing volume: $(VOLUME)"
	-docker volume rm $(VOLUME) 2>/dev/null || true
	@echo "Cleanup complete"

## ----------------------------------------------------------------------------
## Convenience Commands
## ----------------------------------------------------------------------------

## update: Pull latest code, rebuild, and restart (full update cycle)
update: build stop run
	@echo "Update complete!"

## status: Alias for ps
status: ps

## help: Show this help message
help:
	@echo "CoPaw Docker Deployment"
	@echo ""
	@echo "Usage: make <command> [VARIABLE=VALUE ...]"
	@echo ""
	@echo "Commands:"
	@sed -n 's/^## //p' $(MAKEFILE_LIST) | column -t -s ':'
	@echo ""
	@echo "Variables:"
	@echo "  IMAGE      = $(IMAGE)"
	@echo "  CONTAINER  = $(CONTAINER)"
	@echo "  PORT       = $(PORT)"
	@echo "  VOLUME     = $(VOLUME)"
	@echo "  DOCKERFILE = $(DOCKERFILE)"
	@echo ""
	@echo "Examples:"
	@echo "  make build                # Build with defaults"
	@echo "  make run PORT=3000        # Run on custom port"
	@echo "  make update               # Full update cycle"
	@echo "  make clean                # Remove all artifacts"