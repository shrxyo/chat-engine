#!/bin/sh
set -e

# Compose runs migrations once in the `migrate` service and sets
# RUN_MIGRATIONS=false here, so scaled replicas don't race on DDL.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "==> Running database migrations..."
    alembic upgrade head
fi

echo "==> Starting uvicorn (RELOAD=${RELOAD:-false})..."
if [ "${RELOAD:-false}" = "true" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
