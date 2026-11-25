# Site kit (plant side)

The API generates each plant's kit when its operator downloads it (Sites → the plant → Download
kit); nothing here is copied by hand. Templates: `federated-website/FastApi/app/kit/`
(`docker-compose.yml.tmpl`, `docker-compose.gpu.yml`, `tunnel.conf.template`), assembled by
`app/services/site_connection.py: build_kit_zip`.

```
fedwind-site-<id>/
  README.md                personalised steps for this plant
  docker-compose.yml       agent; with COMPOSE_PROFILES=federation also tunnel + supernode
  docker-compose.gpu.yml   GPU for the SuperNode (NVIDIA Container Toolkit)
  tunnel.conf.template     nginx: SuperNode --TLS--> tunnel ==mTLS (plant cert)==> gateway:443
  .env                     site settings, no secrets
  enrollment.token         one use, 72 h
  ca.crt                   ArqauQuat site CA (public)
  data/inbox/              hourly CSV exports (data/README.md)
  secrets/                 filled at enrollment: site-tls.key, site.crt, flower.key(.pub), local-ca.crt, tunnel.crt/.key
  outputs/, hf-cache/      SuperNode outputs; the GPT-2 cache
```

What runs where and why: `SITE_NETWORK_PLAN.md` §1 and §5. Simulated plants for demos and tests:
`deploy/sim/run_site.sh <kit.zip>`.

Still open: the SuperNode trains once the Flower app takes `site`/`energy` node config instead of
partition ids and the agent writes `data/store` (M5/M6); plants need the agent and Flower images
from a registry (pinned by digest) instead of local builds.
