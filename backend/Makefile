.PHONY: run test lint typecheck migrate seed

run:
	PYTHONPATH=src uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

typecheck:
	uv run pyright

migrate:
	uv run alembic upgrade head

seed:
	PYTHONPATH=src uv run python scripts/seed.py
