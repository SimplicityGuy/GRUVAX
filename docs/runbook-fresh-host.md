# GRUVAX Fresh-Host Bring-Up Runbook

This runbook covers the first-time deployment of the GRUVAX Docker Compose stack on a
fresh deployment host (e.g. `your-server.local`). It documents volume permissions,
healthcheck verification, and the expected bring-up sequence.

## Prerequisites

- Docker Engine 26+ with Compose v2 (`docker compose` — no hyphen required)
- A running [discogsography](https://github.com/SimplicityGuy/discogsography) stack on the
  same host (provides the shared Postgres instance)
- A `.env` file in the repo root with at minimum:
  - `SESSION_SECRET` — a long random string (use `python3 -c "import secrets; print(secrets.token_hex(32))"`)
  - `GRUVAX_DB_PASSWORD` — the Postgres password for the `gruvax` user
  - `MQTT_PASSWORD` — the Mosquitto password for `gruvax-api` (optional in dev)

## Volume Permissions

GRUVAX uses **named Docker volumes** for stateful services, not host bind-mounts for
runtime data:

| Volume | Service | Notes |
|--------|---------|-------|
| `gruvax-dev-pg-data` | `gruvax-dev-pg` | Postgres data directory. Managed by the `postgres:18` image (runs as `postgres` uid 999). No chown required. |
| `mosquitto-data` | `mosquitto` | MQTT retained message store. Managed by the `eclipse-mosquitto` image (runs as `mosquitto` uid 1883). No chown required. |
| `mosquitto-log` | `mosquitto` | Mosquitto log directory. Same ownership as above. |
| `mqtt-explorer-data` | `mqtt-explorer` | Debug-profile only. Not started in production. |

The API container (`gruvax-api`) runs as the non-root user `gruvax` (uid created inside
the image at build time). It does **not** write to any host bind-mount directory at
runtime — only the named volumes above are writable, and those are owned by their
respective base-image users.

**On a fresh host, `docker compose up` succeeds without any manual `chown` commands.**
Named volumes are created by the Docker daemon and owned correctly by the service image
that first writes to them.

## Bring-Up Sequence

```bash
# 1. Clone the repo and enter the directory
git clone https://github.com/SimplicityGuy/GRUVAX.git
cd GRUVAX

# 2. Copy and edit the environment file
cp .env.example .env   # or create from scratch (see Prerequisites above)
$EDITOR .env

# 3a. Production host (pull-based deploy — do NOT have compose.override.yaml present):
docker compose pull
docker compose up -d
# Note: the prod host pulls the published GHCR image (ghcr.io/simplicityguy/gruvax:latest).
# Never copy compose.override.yaml to the prod host — if present, docker compose up
# will auto-load it and try to build from source instead of pulling (Pitfall 3).

# 3b. Local dev (build from source via the override):
#   cp compose.override.yaml.example compose.override.yaml
just up-d
# Equivalent to: docker compose up --build -d  (override auto-merges, builds locally)

# 4. Verify all services are healthy (may take 30–60 s on first boot)
docker compose ps
```

Expected output of `docker compose ps` when healthy (production host):

```
NAME            IMAGE                                   STATUS                    PORTS
gruvax-api-1    ghcr.io/simplicityguy/gruvax:latest     Up (healthy)              0.0.0.0:8000->8000/tcp
gruvax-dev-pg   postgres:18                             Up (healthy)              0.0.0.0:5432->5432/tcp
gruvax-...      eclipse-mosquitto:2.1.2-alpine          Up (healthy)
```

All three non-debug services must show `(healthy)` before the kiosk can load.

## Verify Log Driver Configuration

Confirm the `json-file` log driver and rotation limits are applied:

```bash
# Inspect the api container log options
docker inspect gruvax-api-1 --format '{{json .HostConfig.LogConfig}}'
# Expected: {"Type":"json-file","Config":{"max-file":"3","max-size":"10m"}}

# Inspect the mosquitto container
docker inspect $(docker compose ps -q mosquitto) --format '{{json .HostConfig.LogConfig}}'
# Expected: {"Type":"json-file","Config":{"max-file":"3","max-size":"10m"}}

# Inspect the dev-pg container
docker inspect gruvax-dev-pg --format '{{json .HostConfig.LogConfig}}'
# Expected: {"Type":"json-file","Config":{"max-file":"3","max-size":"10m"}}
```

Each service is capped at `10 MB × 3 rotations = 30 MB` of log storage.

## Verify No Permission Errors on Volumes

```bash
# Check for permission-denied entries in the api log
docker compose logs api | grep -i "permission denied" || echo "No permission errors"

# Check mosquitto log
docker compose logs mosquitto | grep -i "permission denied" || echo "No permission errors"

# Check dev-pg log
docker compose logs gruvax-dev-pg | grep -i "permission denied" || echo "No permission errors"
```

## Verify API Health

```bash
curl -sf http://localhost:8000/api/health | python3 -m json.tool
```

Expected response shape:

```json
{
  "status": "ok",
  "db": "ok",
  "discogsography_view_check": "ok",
  "mqtt": "ok",
  "version": "<git-sha>",
  "started_at": "2026-...",
  "sync_age_seconds": null
}
```

If `status` is `"degraded"`, inspect individual fields (`db`, `discogsography_view_check`,
`mqtt`) to identify the failing service.

## Smoke Test (Core Value SLO)

```bash
just demo
```

This runs the full Core Value smoke test:
1. Brings up the stack (builds if needed)
2. Waits for the API to become healthy
3. Searches for "Miles Davis" and asserts `took_ms < 200`
4. Locates the top result and prints the primary cube

A `PASS` message indicates the p95 search SLO is met on the current host.

## Stopping the Stack

```bash
# Stop containers, preserve volumes (DO NOT use -v — that wipes mosquitto-data)
just down
# Equivalent to: docker compose down
```

## Troubleshooting

### API fails to start: "connection refused" to Postgres

The API container depends on `gruvax-dev-pg` becoming healthy (condition:
`service_healthy`). If Postgres is slow to initialize on first boot (it runs
`synth_collection.sql` via the `docker-entrypoint-initdb.d` mechanism), the API will
wait up to 100 seconds (20 retries × 5 s). Check:

```bash
docker compose logs gruvax-dev-pg --tail 20
```

### Mosquitto healthcheck fails

The `mosquitto_sub` healthcheck requires the broker to be fully listening. On first
boot the `mosquitto.conf` is mounted read-only — confirm it is present:

```bash
ls -la mosquitto/mosquitto.conf
```

### API container exits with code 1

Check the API logs for startup errors:

```bash
docker compose logs api --tail 50
```

Common causes: missing `SESSION_SECRET` in `.env`, Postgres migration failure, or
`OBSERVED_DISCOGSOGRAPHY_SCHEMA` pointing to a schema that does not yet exist (run
`just provision-db` to create the required grants).
