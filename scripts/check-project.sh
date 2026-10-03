#!/usr/bin/env bash
# Full validation for bh check/submit: never uses an operator's database.
set -euo pipefail

just setup
just lint
uv run python scripts/check_test_patterns.py
uv run mypy --strict .
npm --prefix frontend run lint
npm --prefix frontend run format:check
just test-spa
just build-spa
uv run playwright install chromium

benchmark=$(mktemp "${TMPDIR:-/tmp}/gruvax-benchmark.XXXXXX")
trap 'rm -f "$benchmark"' EXIT

# Docker chooses an unused loopback port. Every run owns only its container.
container=$(docker run --detach --rm \
  -e POSTGRES_USER=gruvax -e POSTGRES_PASSWORD=gruvax -e POSTGRES_DB=gruvax \
  -p 127.0.0.1::5432 postgres:18)
cleanup() {
  local result=$?
  docker rm --force --volumes "$container" >/dev/null || true
  rm -f "$benchmark"
  exit "$result"
}
trap cleanup EXIT
ready=false
for ((attempt = 0; attempt < 60; attempt++)); do
  if docker exec "$container" pg_isready -U gruvax -d gruvax >/dev/null; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  docker logs "$container"
  exit 1
fi
port=$(docker port "$container" 5432/tcp | sed 's/.*://')
export DATABASE_URL="postgresql+psycopg://gruvax:gruvax@127.0.0.1:${port}/gruvax"
export SESSION_SECRET="ci-test-secret-not-real"
export GRUVAX_SECRET_KEY="tcS1ujQX9eFv2gXr9w8t1V0qBu3UdMVqJTrYqDQ7Wxg="
export DISCOGSOGRAPHY_BASE_URL="http://fake-discogsography:8004"
# aiomqtt/Paho rejects port zero before opening a socket. Lifespan continues
# in degraded mode, and no retained startup message can touch a real broker.
export MQTT_HOST=127.0.0.1
export MQTT_PORT=0
export MQTT_USERNAME=validation
export MQTT_PASSWORD=""
export MQTT_TOPIC_PREFIX="gruvax/v1/dev/leds"
export LOG_LEVEL=WARNING
printf 'Validation database: isolated container %s on loopback port %s\n' "$container" "$port"
docker exec -i "$container" psql -v ON_ERROR_STOP=1 -U gruvax -d gruvax < tests/fixtures/legacy/synth_collection.sql
just migrate-roundtrip
uv run python -m gruvax.db.seed_boundaries fixtures/boundaries.yaml
docker exec -i "$container" psql -v ON_ERROR_STOP=1 -U gruvax -d gruvax < tests/fixtures/synth_profile_collection.sql
# Keep the developer subset ahead of integration tests' shared PIN seeding.
uv run pytest tests/unit/ tests/property/ -ra
# No fail-fast: characterize the entire suite, including browser tests.
uv run pytest tests/ -ra --cov=gruvax --cov-report=term-missing
just slo
uv run pytest tests/unit/test_algorithm.py::test_locate_benchmark \
  --benchmark-only --benchmark-json="$benchmark"
uv run python scripts/check_benchmark.py "$benchmark" --require test_locate_benchmark
