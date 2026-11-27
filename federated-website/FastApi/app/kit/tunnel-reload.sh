#!/bin/sh
# Site kit tunnel: reload nginx when the agent installs a renewed plant certificate (secrets/site.crt).
watch() { cat /pki/site.crt /pki/site-tls.key 2>/dev/null | md5sum; }
(
  last="$(watch)"
  while sleep 30; do
    now="$(watch)"
    if [ "$now" != "$last" ] && nginx -t -q && nginx -s reload; then
      echo "tunnel: reloaded with the renewed certificate"; last="$now"
    fi
  done
) &
