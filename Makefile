.PHONY: dev test lint build

dev:
	@echo "Starting backend and frontend dev servers..."
	@$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	@echo "Running all tests..."
	cd backend && pytest
	cd frontend && npm test

lint:
	@echo "Linting all services..."
	cd backend && ruff check . && mypy .
	cd frontend && npm run lint

build:
	@echo "Building all services..."
	cd frontend && npm run build
	cd infra && docker compose build
