.PHONY: up down restart build install test logs logs-app logs-db ps clean demo real-llm help

ANTHROPIC_API_KEY ?=

.DEFAULT_GOAL := help

## Start all services (build if needed)
up:
	docker compose up --build -d
	@echo ""
	@echo "  Service: http://localhost:8000"
	@echo "  API docs: http://localhost:8000/docs"

## Stop all services
down:
	docker compose down

## Restart the app container only (faster than full rebuild)
restart:
	docker compose restart app

## Rebuild images without starting
build:
	docker compose build

## Install Python test dependencies into the active venv
install:
	pip install -r requirements.txt

## Run the full pytest suite (starts db if not running, uses metering_test DB)
test:
	docker compose up db -d
	@docker compose exec db sh -c 'until pg_isready -U postgres -q; do sleep 1; done'
	pytest tests/ -v

## Follow logs for all services
logs:
	docker compose logs -f

## Follow app logs only
logs-app:
	docker compose logs -f app

## Follow db logs only
logs-db:
	docker compose logs -f db

## Show running service status
ps:
	docker compose ps

## Stop services and delete all volumes (full reset)
clean:
	docker compose down -v

## Start with real Claude API (set ANTHROPIC_API_KEY=sk-... on the command line)
real-llm:
	USE_REAL_LLM=true ANTHROPIC_API_KEY=$(ANTHROPIC_API_KEY) docker compose up --build -d
	@echo ""
	@echo "  Running with ClaudeProvider. Set ANTHROPIC_API_KEY=<key> if not already exported."

## Smoke test: create a user, generate text, check usage (requires 'make up' first)
demo:
	@echo "==> Creating user (quota=10000, multiplier=1.5)..."
	@curl -sf -X POST http://localhost:8000/users/ \
	  -H "Content-Type: application/json" \
	  -d '{"quota": 10000, "multiplier": 1.5}' | python3 -m json.tool
	@echo ""
	@echo "==> Generating text (user 1)..."
	@curl -sf -X POST http://localhost:8000/users/1/generate \
	  -H "Content-Type: application/json" \
	  -d '{"prompt": "Explain the difference between a process and a thread."}' | python3 -m json.tool
	@echo ""
	@echo "==> Current usage..."
	@curl -sf http://localhost:8000/users/1/usage | python3 -m json.tool
	@echo ""
	@echo "==> Usage history..."
	@curl -sf "http://localhost:8000/users/1/usage/history?limit=5" | python3 -m json.tool

## Show available targets
help:
	@echo ""
	@echo "AI Metering and Quota Service"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@awk '/^## /{desc=substr($$0,4); next} /^[a-zA-Z_-]+:/{printf "  %-14s %s\n", $$1, desc; desc=""}' $(MAKEFILE_LIST)
	@echo ""
