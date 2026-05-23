.PHONY: dev dev-backend dev-frontend test lint build

dev:
	@echo "Starting backend and frontend dev servers..."
	@$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd backend && PYTHONPATH=src uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	@echo "Running all tests..."
	cd backend && PYTHONPATH=src uv run pytest
	cd frontend && npm test

lint:
	@echo "Linting all services..."
	cd backend && uv run ruff check src/
	cd frontend && npm run lint

build:
	@echo "Building all services..."
	cd frontend && npm run build
