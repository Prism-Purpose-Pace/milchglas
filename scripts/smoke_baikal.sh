#!/usr/bin/env bash
# GATE-6: the Option B Compose file end to end against a seeded Baikal (spec section 9).
# Runs in CI (job `smoke`) and on any host with Docker and Compose: bash scripts/smoke_baikal.sh
#
# Baikal (plain sabre/dav) reports a calendar shared through its sharing plugin as owned by
# the sharee, so FR-1's check would refuse it; Nextcloud reports the sharing owner. The
# smoke run therefore gives the service user read-only access the sabre way: membership in
# the owner's calendar-proxy-read group. The check sees what it sees on Nextcloud: a
# calendar owned by someone else, readable, not writable.
set -euo pipefail

baikal=docker.io/ckulka/baikal:0.10.1-apache-php8.2@sha256:4f8e5107b15135fefd910efc3f5cc78e13e214c60f4bf2fdec386da6513e7029
caddy=docker.io/library/caddy:2.11-alpine@sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
project=milchglas-smoke
compose() {
  docker compose -p "$project" -f "$root/deploy/option-b/compose.yaml" -f "$work/smoke.yaml" "$@"
}
cleanup() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT
fail() {
  echo "smoke: $1"
  compose logs --no-color 2>&1 | tail -n 60 || true
  exit 1
}

# Throwaway credentials, made per run: nothing here is a secret anywhere else.
owner_pass=$(openssl rand -hex 16)
svc_pass=$(openssl rand -hex 16)
token=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')

echo "certificates: a one-day CA and a leaf for caldav.test"
mkdir -p "$work/certs" "$work/config" "$work/baikal/config" "$work/baikal/Specific/db"
(
  cd "$work/certs"
  openssl req -x509 -newkey rsa:2048 -nodes -days 1 -keyout ca.key -out ca.pem \
    -subj "/CN=milchglas smoke CA" -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign" 2>/dev/null
  openssl req -newkey rsa:2048 -nodes -keyout tls.key -out tls.csr -subj "/CN=caldav.test" 2>/dev/null
  printf 'subjectAltName=DNS:caldav.test\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n' >leaf.ext
  openssl x509 -req -in tls.csr -CA ca.pem -CAkey ca.key -CAcreateserial -days 1 \
    -extfile leaf.ext -out tls.pem 2>/dev/null
  chmod 0644 ./*.pem tls.key
)

echo "baikal: schema from the image, two users, the owner's calendar, proxy-read for the service user"
docker pull -q "$baikal" >/dev/null
docker run --rm --entrypoint cat "$baikal" /var/www/baikal/Core/Resources/Db/SQLite/db.sql >"$work/db.sql"
python3 - "$work/db.sql" "$work/baikal/Specific/db/db.sqlite" "$owner_pass" "$svc_pass" <<'PY'
import hashlib, sqlite3, sys
schema, target, owner_pass, svc_pass = sys.argv[1:]
db = sqlite3.connect(target)
db.executescript(open(schema, encoding="utf-8").read())
def digest(user, password):
    return hashlib.md5(f"{user}:BaikalDAV:{password}".encode()).hexdigest()
db.executemany("INSERT INTO users (username, digesta1) VALUES (?, ?)",
               [("owner", digest("owner", owner_pass)), ("svc", digest("svc", svc_pass))])
principals = [("principals/owner", "owner@smoke.test", "Owner"),
              ("principals/owner/calendar-proxy-read", None, None),
              ("principals/owner/calendar-proxy-write", None, None),
              ("principals/svc", "svc@smoke.test", "Service user")]
db.executemany("INSERT INTO principals (uri, email, displayname) VALUES (?, ?, ?)", principals)
ids = dict(db.execute("SELECT uri, id FROM principals"))
db.execute("INSERT INTO groupmembers (principal_id, member_id) VALUES (?, ?)",
           (ids["principals/owner/calendar-proxy-read"], ids["principals/svc"]))
db.execute("INSERT INTO calendars (id, synctoken, components) VALUES (1, 1, 'VEVENT')")
db.execute("INSERT INTO calendarinstances (calendarid, principaluri, access, displayname, uri,"
           " timezone, transparent) VALUES (1, 'principals/owner', 1, 'Private', 'private',"
           " NULL, 0)")
db.commit()
PY
cat >"$work/baikal/config/baikal.yaml" <<YAML
system:
    configured_version: '0.10.1'
    timezone: 'Europe/Berlin'
    card_enabled: false
    cal_enabled: true
    invite_from: 'noreply@smoke.test'
    dav_auth_type: 'Basic'
    admin_passwordhash: $(openssl rand -hex 16)
    failed_access_message: 'user %u authentication failure for Baikal'
    auth_realm: BaikalDAV
    base_uri: ''
database:
    encryption_key: $(openssl rand -hex 16)
    backend: 'sqlite'
    sqlite_file: '/var/www/baikal/Specific/db/db.sqlite'
YAML
chmod -R a+rwX "$work/baikal"

echo "milchglas: config.json for the owner's calendar, a fresh token and salt"
python3 - "$work/config/config.json" "$token" <<'PY'
import hashlib, json, secrets, sys
path, token = sys.argv[1:]
config = {
    "tz": "Europe/Berlin", "window_days": 33, "grid_minutes": 15, "summary": "Blocker Privat",
    "ttl_seconds": 900, "allday_mode": "busy", "tentative_mode": "busy",
    "owner_emails": ["owner@smoke.test"],
    "calendars": [{"href": "/dav.php/calendars/owner/private/", "name": "Private", "enabled": True}],
    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    "uid_salt": secrets.token_hex(16),
}
with open(path, "w", encoding="utf-8") as file:
    json.dump(config, file)
PY
chmod 0755 "$work/config" && chmod 0644 "$work/config/config.json"

cat >"$work/Caddyfile" <<'CADDY'
{
	admin off
	auto_https disable_redirects
}
https://caldav.test:8443 {
	tls /certs/tls.pem /certs/tls.key
	reverse_proxy baikal:80
}
CADDY

# The production Compose file plus what the smoke run needs: a CalDAV server behind TLS,
# the throwaway config and CA, and the web port on loopback.
cat >"$work/smoke.yaml" <<YAML
services:
  baikal:
    image: $baikal
    volumes:
      - $work/baikal/config:/var/www/baikal/config
      - $work/baikal/Specific:/var/www/baikal/Specific
  caldav:
    image: $caddy
    ports: ["127.0.0.1:8443:8443"]
    volumes:
      - $work/Caddyfile:/etc/caddy/Caddyfile:ro
      - $work/certs:/certs:ro
    networks:
      default:
        aliases: [caldav.test]
  web:
    ports: ["127.0.0.1:8000:8000"]
    volumes:
      - $work/config:/etc/milchglas:ro
  refresher:
    environment:
      SSL_CERT_FILE: /certs/ca.pem
    volumes:
      - $work/config:/etc/milchglas:ro
      - $work/certs/ca.pem:/certs/ca.pem:ro
YAML

export CALDAV_URL=https://caldav.test:8443/ CALDAV_USER=svc CALDAV_SECRET="$svc_pass"
compose build -q
compose up -d baikal caldav
# Every CalDAV request below goes the refresher's way: TLS to caldav.test, checked against the CA.
dav() {
  curl -s --cacert "$work/certs/ca.pem" --resolve caldav.test:8443:127.0.0.1 "$@"
}
calendar=https://caldav.test:8443/dav.php/calendars/owner/private
status=000
for _ in $(seq 1 60); do
  status=$(dav -o /dev/null -w '%{http_code}' -u "svc:$svc_pass" -X PROPFIND -H 'Depth: 0' \
    "$calendar/" || true)
  [ "$status" = "207" ] && break
  sleep 1
done
[ "$status" = "207" ] || fail "the service user's PROPFIND through TLS answered $status"

echo "events: timed, private, cancelled and a daily series, all with sentinel content"
day=$(date -u -d tomorrow +%Y%m%d)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
put() {
  local uid=$1 body=$2
  local code
  code=$(printf 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//milchglas//smoke//EN\r\nBEGIN:VEVENT\r\nUID:%s\r\nDTSTAMP:%s\r\n%sEND:VEVENT\r\nEND:VCALENDAR\r\n' \
    "$uid" "$stamp" "$body" |
    dav -o /dev/null -w '%{http_code}' -u "owner:$owner_pass" -X PUT \
      -H 'Content-Type: text/calendar; charset=utf-8' --data-binary @- "$calendar/$uid.ics")
  [ "$code" = "201" ] || fail "PUT $uid answered $code"
}
put smoke-timed "DTSTART:${day}T090000Z\r\nDTEND:${day}T100000Z\r\nSUMMARY:BBX-SMOKE-TIMED\r\nLOCATION:BBX-SMOKE-ROOM\r\n"
put smoke-private "DTSTART:${day}T130700Z\r\nDTEND:${day}T135200Z\r\nCLASS:PRIVATE\r\nSUMMARY:BBX-SMOKE-PRIVATE\r\n"
put smoke-cancelled "DTSTART:${day}T160000Z\r\nDTEND:${day}T170000Z\r\nSTATUS:CANCELLED\r\nSUMMARY:BBX-SMOKE-CANCELLED\r\n"
put smoke-daily "DTSTART:${day}T060000Z\r\nDTEND:${day}T063000Z\r\nRRULE:FREQ=DAILY;COUNT=3\r\nSUMMARY:BBX-SMOKE-DAILY\r\nDESCRIPTION:BBX-SMOKE-NOTES\r\n"

echo "compose: web and refresher from the production file"
compose up -d web refresher
health=000
for _ in $(seq 1 60); do
  health=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/healthz || true)
  [ "$health" = "200" ] && break
  sleep 1
done
[ "$health" = "200" ] || fail "/healthz answered $health after 60 s"

echo "feed: right token 200 with the expected blocks, wrong token the identical 404"
headers=$work/headers
curl -s -D "$headers" -o "$work/feed.ics" "http://127.0.0.1:8000/f/$token.ics"
grep -q '^HTTP/1.1 200' "$headers" || fail "the feed did not answer 200"
grep -qi '^content-type: text/calendar; charset=utf-8' "$headers" || fail "wrong content type"
events=$(grep -c '^BEGIN:VEVENT' "$work/feed.ics" || true)
[ "$events" = "5" ] || fail "expected 5 blocks (timed, private, 3 daily), got $events"
for line in "DTSTART:${day}T090000Z" "DTSTART:${day}T130000Z" "DTEND:${day}T140000Z" \
  "DTSTART:${day}T060000Z"; do
  grep -q "^$line" "$work/feed.ics" || fail "the feed lacks $line"
done
if grep -q "T160000Z" "$work/feed.ics"; then fail "the cancelled event reached the feed"; fi
wrong=$(curl -s -w '%{http_code}' "http://127.0.0.1:8000/f/not-the-token.ics")
unknown=$(curl -s -w '%{http_code}' "http://127.0.0.1:8000/nothing-here")
if [ "$wrong" != "$unknown" ] || [ "${wrong: -3}" != "404" ]; then
  fail "a wrong token and an unknown path differ"
fi

echo "leaks: no sentinel, token or secret in the feed, the state or any log"
compose exec -T refresher cat /var/lib/milchglas/state.json >"$work/state.json"
compose logs --no-color web refresher >"$work/logs.txt" 2>&1
for file in feed.ics state.json logs.txt; do
  if grep -q -e 'BBX-' -e "$token" -e "$svc_pass" "$work/$file"; then fail "a private value reached $file"; fi
done

echo "refresher: docker stop lets the loop exit 0 within Docker's default 10 s"
started=$(date +%s)
compose stop refresher >/dev/null
elapsed=$(( $(date +%s) - started ))
code=$(docker inspect --format '{{.State.ExitCode}}' "$(compose ps -a -q refresher)")
if [ "$code" != "0" ] || [ "$elapsed" -ge 10 ]; then fail "refresher exit $code after ${elapsed}s"; fi
echo "smoke run passed"
