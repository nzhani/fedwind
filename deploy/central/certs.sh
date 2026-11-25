#!/usr/bin/env bash
# Public certificates for the gateway from Let's Encrypt (HTTP-01 through the gateway on port 80).
#
#   deploy/central/certs.sh issue    first time, once DNS for WEB_HOST and SITES_HOST points here
#   deploy/central/certs.sh renew    from cron, e.g. daily:  17 3 * * *  /path/to/deploy/central/certs.sh renew
#
# Certificates land in the gateway-certs volume (live/<host>/fullchain.pem, privkey.pem); the gateway
# notices the change and reloads within 30 s. Plant client certificates come from the site CA (API),
# not from here.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[[ -f "$HERE/.env" ]] || { echo "Missing $HERE/.env (copy .env.example)" >&2; exit 1; }
set -a; source "$HERE/.env"; set +a
: "${WEB_HOST:?}" "${SITES_HOST:?}" "${ACME_EMAIL:?set ACME_EMAIL in .env}"
dc=(docker compose -f "$HERE/docker-compose.yml" --profile tools)

# Copy certbot's current certificate for <host> over the gateway's files (dereferencing its symlinks)
install_cert() {
  "${dc[@]}" run --rm --entrypoint sh certbot -c "
    set -e
    mkdir -p /certs/live/$1
    cp -L /etc/letsencrypt/live/$1/fullchain.pem /certs/live/$1/.fullchain.pem
    cp -L /etc/letsencrypt/live/$1/privkey.pem   /certs/live/$1/.privkey.pem
    chmod 600 /certs/live/$1/.privkey.pem
    mv /certs/live/$1/.privkey.pem   /certs/live/$1/privkey.pem
    mv /certs/live/$1/.fullchain.pem /certs/live/$1/fullchain.pem"
}

case "${1:-}" in
  issue)
    for host in "$WEB_HOST" "$SITES_HOST"; do
      "${dc[@]}" run --rm certbot certonly --webroot -w /var/www/acme -d "$host" --cert-name "$host" \
        --email "$ACME_EMAIL" --agree-tos --no-eff-email --non-interactive --keep-until-expiring
      install_cert "$host"
      echo "certificate for $host installed"
    done
    ;;
  renew)
    "${dc[@]}" run --rm certbot renew --webroot -w /var/www/acme --non-interactive --quiet
    for host in "$WEB_HOST" "$SITES_HOST"; do install_cert "$host"; done
    ;;
  *)
    echo "usage: deploy/central/certs.sh issue|renew" >&2; exit 2 ;;
esac
