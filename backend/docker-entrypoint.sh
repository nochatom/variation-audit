#!/bin/sh
# Run DB migrations (API container only) then exec the container command.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] applying alembic migrations..."
  i=1
  while [ "$i" -le 6 ]; do
    if alembic upgrade head; then
      break
    fi
    echo "[entrypoint] DB not ready, retry $i/6..."
    i=$((i + 1))
    sleep 3
  done
fi

exec "$@"
