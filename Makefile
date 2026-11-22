.PHONY: install dev dev-backend dev-frontend test lint typecheck build clean load-test

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

# S6.4 — k6 WebSocket flood through nginx over REPLICAS backends.
# Seeds VUS users (rooms of ROOM_SIZE) on the host, then runs k6 in the compose
# network. Report: docs/benchmarks/$(RUN_NAME)/{report.html,summary.json}.
# Example: make load-test VUS=1000 REPLICAS=3 RAMP=2m HOLD=5m RUN_NAME=1k-3r
LOADTEST_COMPOSE = docker compose -f docker-compose.yml -f infra/load-tests/compose.loadtest.yml
REPLICAS ?= 3
VUS ?= 100
ROOM_SIZE ?= 10
RAMP ?= 1m
HOLD ?= 3m
SEND_INTERVAL_S ?= 5
SESSION_S ?= 120
RUN_NAME ?= latest

load-test:
	$(LOADTEST_COMPOSE) up -d --wait --scale backend=$(REPLICAS) nginx
	$(MAKE) -C backend loadtest-seed USERS=$(VUS) ROOM_SIZE=$(ROOM_SIZE)
	mkdir -p docs/benchmarks/$(RUN_NAME)
	VUS=$(VUS) RAMP=$(RAMP) HOLD=$(HOLD) SEND_INTERVAL_S=$(SEND_INTERVAL_S) \
	SESSION_S=$(SESSION_S) RUN_NAME=$(RUN_NAME) \
	$(LOADTEST_COMPOSE) --profile loadtest run --rm --no-deps k6 \
		run --summary-export /out/summary.json websocket_flood.js
