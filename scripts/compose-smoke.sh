#!/usr/bin/env bash
# Disposable development stack: no operator env, ports, volumes, or image tags.
set -euo pipefail
cd "$(dirname "$0")/.."
scratch=$(mktemp -d "${TMPDIR:-/tmp}/gruvax-compose-smoke.XXXXXX")
project="gruvax-smoke-$(basename "$scratch" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-')"
cat >"$scratch/env" <<'ENV'
GRUVAX_ENV=development
DATABASE_URL=postgresql+psycopg://gruvax:gruvax@gruvax-dev-pg:5432/gruvax
DISCOGSOGRAPHY_BASE_URL=http://fake-discogsography:8004
GRUVAX_DB_USER=gruvax
GRUVAX_DB_PASSWORD=gruvax
GRUVAX_DB_NAME=gruvax
GRUVAX_SECRET_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
SESSION_SECRET=isolated-compose-smoke-only
GRUVAX_ADMIN_PIN=123456
MQTT_HOST=mosquitto
MQTT_PORT=1883
MQTT_USERNAME=gruvax-api
MQTT_PASSWORD=
ENV
cat >"$scratch/override.yaml" <<YAML
services:
  api:
    image: $project-api:local
    env_file: !override
      - $scratch/env
    ports: !override
      - "127.0.0.1::8000"
  init-sync:
    image: $project-api:local
    container_name: $project-init-sync
  gruvax-dev-pg:
    container_name: $project-pg
    ports: !override
      - "127.0.0.1::5432"
  fake-discogsography:
    image: $project-fake:local
    container_name: $project-fake
YAML
# Ignore inherited configuration, including external DATABASE_URL/MQTT overrides.
compose() {
  env -i PATH="$PATH" HOME="$HOME" DOCKER_HOST="${DOCKER_HOST:-}" \
    docker compose --project-name "$project" --env-file "$scratch/env" \
    -f compose.yaml -f "$scratch/override.yaml" --profile dev "$@"
}
cleanup() {
  result=$?
  if ((result != 0)); then compose logs --tail=100 >&2 || true; fi
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  docker image rm "$project-api:local" "$project-fake:local" >/dev/null 2>&1 || true
  rm -rf "$scratch"
  exit "$result"
}
trap cleanup EXIT
compose up --build -d api fake-discogsography init-sync
container=$(compose ps --all --quiet init-sync)
api_container=$(compose ps --quiet api)
[[ "$(docker inspect "$container" --format '{{.Image}}')" == "$(docker inspect "$api_container" --format '{{.Image}}')" ]]
echo "API and init-sync use the exact same image ID"
for ((attempt = 0; attempt < 60; attempt++)); do
  state=$(docker inspect "$container" --format '{{.State.Status}}')
  if [[ "$state" == exited ]]; then break; fi
  sleep 2
done
[[ "$state" == exited ]]
[[ "$(docker inspect "$container" --format '{{.State.ExitCode}}')" == 0 ]]
compose exec -T fake-discogsography python -c \
  "import urllib.request as u, json; req = u.Request('http://127.0.0.1:8004/api/user/collection?limit=1', headers={'Authorization': 'Bearer dscg_dev_seed'}); body = json.loads(u.urlopen(req).read()); assert len(body['releases']) > 0, body"
