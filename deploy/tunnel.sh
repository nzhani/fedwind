#!/usr/bin/env bash
# Public link to the ArqauQuat website running on this laptop.
#
#   deploy/tunnel.sh on       switch on and print the link to send to people
#   deploy/tunnel.sh off      switch off; the link stops working at once
#   deploy/tunnel.sh status   on or off, and the current link
#
# Default: localhost.run, an SSH tunnel (no account; works on networks that block Cloudflare's
# tunnel port). Its free address changes now and then: run `status` before sending it again.
# TUNNEL=cloudflare deploy/tunnel.sh on   uses a Cloudflare quick tunnel instead (needs outbound
# port 7844, which some networks block).
#
# While it's on, links in Telegram messages and in downloaded site kits use the public address;
# `off` points them back at localhost. The stack must be running (deploy/docker-compose.yml).
# Nothing starts by itself after a reboot.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
[[ -f "$REPO/deploy/sim/demo.env" ]] && source "$REPO/deploy/sim/demo.env"
export FEDWIND_DATA="${FEDWIND_DATA:-$HOME/fedwind-demo-data}"
dc=(docker compose -f "$REPO/deploy/docker-compose.yml" --profile tunnel)
STATE="$REPO/deploy/.tunnel"
mkdir -p "$STATE"
[[ -f "$STATE/.gitignore" ]] || echo "*" > "$STATE/.gitignore"
LOG="$STATE/tunnel.log"
PIDF="$STATE/tunnel.pid"
CF=fedwind-tunnel-1

# -- localhost.run (SSH) --------------------------------------------------------------------------
ssh_running() { [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }
ssh_link() { grep -oE 'https://[a-z0-9]+(\.[a-z0-9]+)*\.lhr\.life' "$LOG" 2>/dev/null | tail -1 || true; }
ssh_start() {
  : > "$LOG"
  # Its own session, so `off` stops the loop and ssh together; reconnects if the connection drops.
  # No keys are offered (the free tier needs none); localhost.run's host key is kept in deploy/.tunnel.
  setsid bash -c '
    while true; do
      ssh -T -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$0/known_hosts" \
          -o PubkeyAuthentication=no -o IdentityAgent=none -o IdentitiesOnly=yes \
          -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
          -R 80:localhost:3000 nokey@localhost.run
      echo "--- connection closed; reconnecting in 5 s"
      sleep 5
    done' "$STATE" >> "$LOG" 2>&1 < /dev/null &
  echo $! > "$PIDF"
}
ssh_stop() { [[ -f "$PIDF" ]] && kill -- -"$(cat "$PIDF")" 2>/dev/null || true; rm -f "$PIDF"; }

# -- Cloudflare quick tunnel (compose service "tunnel") -------------------------------------------
cf_running() { [[ "$(docker inspect -f '{{.State.Running}}' "$CF" 2>/dev/null || true)" == "true" ]]; }
cf_link() { docker logs "$CF" 2>&1 | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true; }

current() {
  if ssh_running && [[ -n "$(ssh_link)" ]]; then ssh_link
  elif cf_running && [[ -n "$(cf_link)" ]]; then cf_link
  fi
}

# Where Telegram messages and site kits point: the public link, or localhost when empty
point_links_at() {
  if [[ -n "$1" ]]; then
    PUBLIC_WEB_URL="$1" PUBLIC_API_URL="$1" "${dc[@]}" up -d --no-deps api >/dev/null 2>&1
  else
    "${dc[@]}" up -d --no-deps api >/dev/null 2>&1
  fi
}

case "${1:-status}" in
  on)
    [[ "$(docker inspect -f '{{.State.Running}}' fedwind-web-1 2>/dev/null || true)" == "true" ]] \
      || { echo "The website isn't running. Start the stack first (deploy/docker-compose.yml)." >&2; exit 1; }
    url="$(current)"
    if [[ -z "$url" ]]; then
      if [[ "${TUNNEL:-localhost.run}" == "cloudflare" ]]; then
        "${dc[@]}" up -d --no-deps tunnel >/dev/null 2>&1
        for _ in $(seq 1 30); do url="$(cf_link)"; [[ -n "$url" ]] && break; sleep 1; done
      else
        ssh_running || ssh_start
        for _ in $(seq 1 30); do url="$(ssh_link)"; [[ -n "$url" ]] && break; sleep 1; done
      fi
      [[ -n "$url" ]] || { echo "No public link yet. Log: $LOG (or: docker logs $CF)" >&2; exit 1; }
    fi
    echo "Pointing Telegram and site-kit links at $url ..."
    point_links_at "$url"
    printf "Checking the link"
    ok=""
    for _ in $(seq 1 30); do
      [[ "$(curl -s -o /dev/null -w '%{http_code}' -m 8 "$url/" || true)" == "200" ]] && { ok=1; break; }
      printf "."; sleep 2
    done
    echo
    if [[ -n "$ok" ]]; then
      echo
      echo "  ON:  $url"
      echo
      echo "Anyone with this link can open the site and register. Switch off with: deploy/tunnel.sh off"
    else
      echo "The tunnel is up but $url doesn't answer yet; try it in a minute, or run: deploy/tunnel.sh off" >&2
      exit 1
    fi
    ;;
  off)
    was=""
    if ssh_running || [[ -f "$PIDF" ]]; then ssh_stop; was=1; fi
    if docker inspect "$CF" >/dev/null 2>&1; then "${dc[@]}" rm -sf tunnel >/dev/null 2>&1; was=1; fi
    if [[ -n "$was" ]]; then
      point_links_at ""
      echo "OFF: the public link no longer works. The site still runs on http://localhost:3000"
    else
      echo "Already off."
    fi
    ;;
  status)
    url="$(current)"
    if [[ -n "$url" ]]; then echo "ON:  $url"; else echo "OFF"; fi
    ;;
  *)
    echo "usage: deploy/tunnel.sh on|off|status   (TUNNEL=cloudflare for a Cloudflare tunnel)" >&2
    exit 2
    ;;
esac
