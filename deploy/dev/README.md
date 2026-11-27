# Scale and security tests (SITE_NETWORK_PLAN.md M9)

For a **test** deployment of the central stack (`deploy/central`), not a laptop: 20 simulated plants
each run a Flower SuperNode with GPT-2 (32 GB+ RAM, a GPU helps).

| Script | What it does |
|---|---|
| `spawn_sites.sh N [wind\|solar]` | Registers, approves and issues kits for N plants through the platform's own services (CLI `sim-plants spawn`), then installs each kit with `deploy/sim/run_site.sh`: agent, tunnel and SuperNode, NASA POWER data at real Kazakh plant regions. `SIM_ALLOW=1` confirms a test server. |
| `spawn_sites.py N --admin <email> [--api URL]` | The same plants made through the website's HTTP API like people would (admin login at a hidden prompt), also against a remote server; kits go to `kits/`, start them with `spawn_sites.sh --start deploy/dev/kits`. |
| `stop_sites.sh [--forget]` | Stops every simulated plant ("Sim ..." names). |
| `load_test.sh` | 20 plants, 3 rounds; one plant's SuperNode is stopped after round 1 (must show as **dropped**), one sends NaN updates (`FEDWIND_TEST_POISON`, must show as **rejected**). Writes `results/load_test_<time>.json` with PASS/FAIL per check. |
| `security_check.py` | The threat checks of §2.4 from outside the server: open ports, no certificate, a certificate from another CA, a revoked certificate, the Flower Control API not routed, the site API hidden from browsers, forged headers, token and login rate limits, HSTS. Exit code 1 if any fails. |

Useful CLI commands (inside the api container):

```bash
docker compose -f deploy/central/docker-compose.yml exec api python -m app.cli sim-plants status
docker compose -f deploy/central/docker-compose.yml exec api python -m app.cli start-run --energy wind --rounds 3 --horizon 1 --data-percent 5
docker compose -f deploy/central/docker-compose.yml exec api python -m app.cli run-status <run_id>
```

Order: start `deploy/central`, `SIM_ALLOW=1 deploy/dev/load_test.sh`, then from another machine
`python3 deploy/dev/security_check.py --address <ip> --web-host <web> --sites-host <sites> [--insecure]`.
