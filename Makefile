.PHONY: install dev-install dev run lint test clean build frontend-install frontend-dev frontend-build frontend-test

install:  ## Install production dependencies
	pip install -e .

dev-install:  ## Install with dev dependencies
	pip install -e ".[dev]"

dev:  ## Show full-stack development instructions
	@echo "Start backend:  make run"
	@echo "Start frontend: make frontend-dev"
	@echo "Run both in separate terminals"

run:  ## Start the application
	uvicorn app.main:app --reload --port 8000

lint:  ## Run linter
	ruff check app/ tests/

format:  ## Format code
	ruff format app/ tests/

test:  ## Run tests
	pytest tests/ -v

clean:  ## Remove build artifacts
	rm -rf __pycache__ app/__pycache__ app/routes/__pycache__
	rm -rf *.egg-info dist build .pytest_cache .ruff_cache

build: frontend-build  ## Build frontend for production and show next steps
	@echo "Frontend built to app/static/dist/"
	@echo "Start with: make run"

# Frontend
frontend-install:  ## Install frontend dependencies
	cd frontend && npm install

frontend-dev:  ## Start frontend dev server
	cd frontend && npm run dev

frontend-build:  ## Build frontend for production
	cd frontend && npm run build

frontend-test:  ## Run frontend tests
	cd frontend && npm test

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
