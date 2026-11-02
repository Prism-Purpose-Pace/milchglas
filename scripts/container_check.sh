#!/usr/bin/env bash
# Build the Option B image and check it and a hardened `web` container (spec section 9).
# Runs in CI (job `container`) and on any host with Docker: bash scripts/container_check.sh
# Not yet covered here: the Baikal smoke run and the refresher's SIGTERM in a container.
set -euo pipefail

image=milchglas:check
name=milchglas-check-web
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm -f milchglas-check-state >/dev/null 2>&1 || true
  rm -rf "${config_dir:-}"
}
trap cleanup EXIT

docker build --pull --tag "$image" .

echo "image: non-root user, no CalDAV value, no test tooling"
user=$(docker image inspect --format '{{.Config.User}}' "$image")
[ "$user" = "10001:10001" ] || { echo "user is '$user'"; exit 1; }
if docker image inspect --format '{{json .Config.Env}}' "$image" | grep -q CALDAV_; then
  echo "the image config names a CALDAV_ variable"; exit 1
fi
docker run --rm --entrypoint python "$image" -c '
import importlib.util, sys, zoneinfo
assert zoneinfo.TZPATH == (), zoneinfo.TZPATH  # the pinned tzdata decides
for tool in ("pytest", "hypothesis", "mypy", "ruff", "pip"):
    assert importlib.util.find_spec(tool) is None, tool
import gunicorn, icalendar, milchglas  # the runtime dependencies are there
'

echo "web: read-only root, tmpfs /tmp, no capabilities, no-new-privileges"
config_dir=$(mktemp -d)
chmod 0755 "$config_dir"
docker volume create milchglas-check-state >/dev/null
docker run -d --name "$name" \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
  -v milchglas-check-state:/var/lib/milchglas:ro -v "$config_dir":/etc/milchglas:ro \
  -p 127.0.0.1:8000:8000 "$image" >/dev/null

for _ in $(seq 1 30); do
  status=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/healthz || true)
  [ "$status" != "000" ] && break
  sleep 1
done
# No state and no config yet: /healthz must say 503, and the container stay healthy.
[ "$status" = "503" ] || { echo "/healthz answered $status"; docker logs "$name"; exit 1; }
for _ in $(seq 1 30); do
  health=$(docker inspect --format '{{.State.Health.Status}}' "$name")
  [ "$health" = "healthy" ] && break
  sleep 2
done
[ "$health" = "healthy" ] || { echo "health is $health with /healthz 503"; exit 1; }
[ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/f/wrong.ics)" = "404" ]
[ "$(docker exec "$name" id -u)" != "0" ]
changed=$(docker diff "$name" | grep -v -E ' /tmp(/|$)' || true)
[ -z "$changed" ] || { echo "writes outside the volume and /tmp:"; echo "$changed"; exit 1; }
if docker logs "$name" 2>&1 | grep -i -E 'control.?socket|warning'; then
  echo "gunicorn logged a warning at start"; exit 1
fi
docker inspect --format '{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.CapDrop}} {{.HostConfig.SecurityOpt}}' "$name"
echo "container check passed"
