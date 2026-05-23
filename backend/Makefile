.PHONY: install run worker test lint format typecheck migrate migration seed

install:
	uv sync

run:
	PYTHONPATH=src uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# arq AI worker (Epic 5). Requires backend/src/app/worker/main.py:WorkerSettings.
worker:
	PYTHONPATH=src uv run arq app.worker.main.WorkerSettings

test:
	uv run pytest

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

typecheck:
	uv run pyright

migrate:
	uv run alembic upgrade head

# Generate a new migration. Usage: make migration name="add_foo_column"
migration:
	@if [ -z "$(name)" ]; then echo "usage: make migration name=<short_snake_case>"; exit 1; fi
	uv run alembic revision --autogenerate -m "$(name)"

seed:
	PYTHONPATH=src uv run python scripts/seed.py
