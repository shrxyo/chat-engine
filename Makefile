.PHONY: install dev dev-backend dev-frontend test lint typecheck build clean

install:
	@echo "Installing backend and frontend deps..."
	$(MAKE) -C backend install
	$(MAKE) -C frontend install

dev:
	@echo "Starting backend and frontend dev servers..."
	@$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	$(MAKE) -C backend run

dev-frontend:
	$(MAKE) -C frontend dev

test:
	@echo "Running all tests..."
	$(MAKE) -C backend test
	$(MAKE) -C frontend test

lint:
	@echo "Linting all services..."
	$(MAKE) -C backend lint
	$(MAKE) -C frontend lint

typecheck:
	@echo "Type-checking all services..."
	$(MAKE) -C backend typecheck
	$(MAKE) -C frontend typecheck

build:
	@echo "Building frontend..."
	$(MAKE) -C frontend build

clean:
	docker compose down -v
	rm -rf backend/.venv backend/.pytest_cache backend/.ruff_cache backend/htmlcov
	rm -rf frontend/.next frontend/node_modules/.cache
