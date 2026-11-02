#!/usr/bin/env bash
# Build the Option B image and check it and a hardened `web` container (spec section 9).
# Runs in CI (job `container`) and on any host with Docker: bash scripts/container_check.sh
# Not yet covered here: the Baikal smoke run.
set -euo pipefail

image=milchglas:check
name=milchglas-check-web
refresher=milchglas-check-refresher
cleanup() {
  docker rm -f "$name" "$refresher" >/dev/null 2>&1 || true
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
# web refuses to start without a valid token_sha256 (WEB-13): the digest of a throwaway value.
digest=$(printf 'container-check' | sha256sum | cut -d' ' -f1)
printf '{"token_sha256": "%s"}\n' "$digest" >"$config_dir/config.json"
chmod 0644 "$config_dir/config.json"
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
# No state yet (no last success): /healthz must say 503, and the container stay healthy.
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

echo "web: a malformed request line leaves no token in the log (WEB-21)"
token=SYNTHETICfeedTOKEN0123456789abcdefghijklmno  # synthetic, shaped like a feed token
for line in "GET /f/$token.ics" "GET /f/$token.ics HTTP/1.1 extra" "GET /f/$token.ics HTTP/9.9"; do
  exec 3<>/dev/tcp/127.0.0.1/8000
  printf '%s\r\nHost: x\r\n\r\n' "$line" >&3
  head -c 12 <&3 | grep -q '^HTTP/1.1 400' || { echo "no 400 for a malformed line"; exit 1; }
  exec 3<&- 3>&-
done
sleep 1
docker logs "$name" 2>&1 | grep -q 'Invalid request; the request line is withheld' \
  || { echo "gunicorn logged no constant line"; exit 1; }
if docker logs "$name" 2>&1 | grep -q "$token"; then
  echo "the token reached the web log"; exit 1
fi

echo "refresher: the image runs refresh --loop and stops on SIGTERM (#111)"
docker run --rm --entrypoint python "$image" -m milchglas refresh --help >/dev/null \
  || { echo "the image has no refresh command"; exit 1; }
# An unreachable source: each run fails and the loop waits for its next slot.
docker run -d --name "$refresher" \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
  --tmpfs /var/lib/milchglas:uid=10001,gid=10001,mode=0700 -v "$config_dir":/etc/milchglas:ro \
  -e CALDAV_URL=https://127.0.0.1:1/ -e CALDAV_USER=check -e CALDAV_SECRET=check \
  -e MILCHGLAS_LOG_LEVEL=INFO --no-healthcheck \
  --entrypoint python "$image" -m milchglas refresh --loop --interval 900 >/dev/null
for _ in $(seq 1 30); do
  docker logs "$refresher" 2>&1 | grep -q 'refresh failed' && break
  sleep 1
done
docker logs "$refresher" 2>&1 | grep -q 'refresh failed' \
  || { echo "the refresher logged no run"; docker logs "$refresher"; exit 1; }
started=$(date +%s)
docker stop --time 20 "$refresher" >/dev/null
elapsed=$(( $(date +%s) - started ))
code=$(docker inspect --format '{{.State.ExitCode}}' "$refresher")
[ "$code" = "0" ] && [ "$elapsed" -lt 15 ] \
  || { echo "SIGTERM: exit $code after ${elapsed}s"; docker logs "$refresher"; exit 1; }
echo "container check passed"
