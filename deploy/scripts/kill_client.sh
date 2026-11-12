#!/usr/bin/env bash
# Fault-tolerance test (plan T4.4, FR-13): stop one client mid-round, then bring it back.
#   deploy/scripts/kill_client.sh aktau 120     # stop client-aktau for 120 s
# The round should finish with the other clients and the dashboard shows the site as dropped.
set -euo pipefail
SITE="${1:?site id, e.g. aktau}"
DOWN_S="${2:-120}"
COMPOSE=(docker compose -f "$(dirname "$0")/../docker-compose.yml")
"${COMPOSE[@]}" stop "client-$SITE"
echo "client-$SITE stopped; restarting in ${DOWN_S}s"
sleep "$DOWN_S"
"${COMPOSE[@]}" start "client-$SITE"
