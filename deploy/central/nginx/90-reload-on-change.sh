#!/bin/sh
# nginx reads certificates and the CRL only at (re)load. The API re-publishes the CRL on every
# revocation and hourly; certs.sh renews the public certificates. Reload within 30 s of a change.
watch() { cat /site-ca/crl.pem /site-ca/ca.crt /certs/live/*/fullchain.pem 2>/dev/null | md5sum; }
(
  last="$(watch)"
  while sleep 30; do
    now="$(watch)"
    if [ "$now" != "$last" ]; then
      # A broken file keeps the old config running; retried on the next check
      if nginx -t -q && nginx -s reload; then echo "gateway: reloaded (CRL or certificate changed)"; last="$now"; fi
    fi
  done
) &
