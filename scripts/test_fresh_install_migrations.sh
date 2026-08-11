#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/ops/compose/p2e1-fresh-install.yml"
PROJECT_NAME="${P2E1_COMPOSE_PROJECT_NAME:-vag-p2e1-$PPID-$$}"

if [[ "$PROJECT_NAME" != vag-p2e1-* ]]; then
  echo "P2E1_COMPOSE_PROJECT_NAME must start with vag-p2e1- for isolation." >&2
  exit 64
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for the P2.0e.1 fresh-install E2E." >&2
  exit 69
fi

docker compose version >/dev/null

compose=(docker compose --project-name "$PROJECT_NAME" --file "$COMPOSE_FILE")

cleanup() {
  "${compose[@]}" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

printf 'P2.0e.1 isolated Compose project: %s\n' "$PROJECT_NAME"

"${compose[@]}" up -d --wait postgres runtime-control-redis

public_table_count="$(
  "${compose[@]}" exec -T postgres \
    psql -U governance -d governance_fresh_install -Atc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
)"
if [[ "$public_table_count" != "0" ]]; then
  echo "Fresh-install precondition failed: PostgreSQL is not empty." >&2
  exit 1
fi

"${compose[@]}" build migrate api

printf '%s\n' '--- first alembic upgrade head ---'
"${compose[@]}" run --rm migrate

printf '%s\n' '--- alembic current after fresh install ---'
current_output="$(
  "${compose[@]}" run --rm migrate alembic -c /workspace/alembic.ini current 2>&1
)"
printf '%s\n' "$current_output"
if ! grep -Eq '0019 \(head\)' <<<"$current_output"; then
  echo "Expected Alembic current revision 0019 (head)." >&2
  exit 1
fi

printf '%s\n' '--- second alembic upgrade head ---'
"${compose[@]}" run --rm migrate

printf '%s\n' '--- current revision after second upgrade ---'
second_current_output="$(
  "${compose[@]}" run --rm migrate alembic -c /workspace/alembic.ini current 2>&1
)"
printf '%s\n' "$second_current_output"
if ! grep -Eq '0019 \(head\)' <<<"$second_current_output"; then
  echo "Alembic head changed after the idempotence check." >&2
  exit 1
fi

printf '%s\n' '--- API readiness ---'
"${compose[@]}" up -d --no-deps api

readiness_output=""
for _attempt in $(seq 1 40); do
  if readiness_output="$(
    "${compose[@]}" exec -T api python -c \
      'import json, urllib.request; response = urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=3); payload = json.load(response); assert response.status == 200; assert payload["status"] == "ok"; assert payload["checks"]["database"] == "ok"; assert payload["checks"]["schema"] == "ok"; assert payload["checks"]["runtime_control"] == "ok"; print(json.dumps(payload, sort_keys=True))' \
      2>/dev/null
  )"; then
    printf '%s\n' "$readiness_output"
    printf '%s\n' 'P2.0e.1 fresh-install E2E: PASS'
    exit 0
  fi
  sleep 1
done

"${compose[@]}" logs api postgres runtime-control-redis >&2 || true
echo "API readiness did not become healthy." >&2
exit 1
