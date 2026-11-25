#!/usr/bin/env bash
# From a machine OUTSIDE the server: which TCP ports of the central server answer.
# Expected: 80 and 443 open (22 too if you administer it over SSH), nothing else.
#
#   deploy/central/check_ports.sh <server address>
set -uo pipefail
host="${1:?usage: check_ports.sh <server address>}"
ports=(22 80 443 3000 5432 8000 8001 9091 9092 9093 9094)
bad=0
for p in "${ports[@]}"; do
  if timeout 3 bash -c "exec 3<>/dev/tcp/$host/$p" 2>/dev/null; then
    case "$p" in
      80|443) echo "  $p open   (gateway)";;
      22)     echo "  $p open   (SSH: restrict it to the admins' addresses)";;
      *)      echo "  $p OPEN   <- must not be reachable"; bad=1;;
    esac
  else
    echo "  $p closed"
  fi
done
# Without a plant certificate the site API must refuse (SITES_HOST=sites.example.kz check_ports.sh <address>)
if [[ -n "${SITES_HOST:-}" ]]; then
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 8 --resolve "$SITES_HOST:443:$host" \
          "https://$SITES_HOST/site-api/heartbeat" -X POST || true)"
  echo "  site API without a certificate: HTTP $code (expect 403)"
  [[ "$code" == "403" ]] || bad=1
fi
exit $bad
