# Gateway spike (M0 of SITE_NETWORK_PLAN.md)

Proves that Flower 1.25.0 works behind an mTLS gateway, with plant-generated credentials, and that
nothing that carries model updates is reachable without a plant certificate.

```
plant LAN                         "internet"                           central server (private)
supernode ──TLS──► tunnel (nginx) ══mTLS: plant cert══► gateway (nginx) ──TLS──► superlink :9092
  node key (SSH EC P-384)          client cert, CN=site      verifies site CA + CRL     --enable-supernode-auth
                                                              proxies Fleet API only     Control :9093 / ServerAppIo :9091 internal
admin (inside the server): flwr supernode register|list|unregister, flwr run — over the TLS Control API
```

## Run it

```bash
./make_certs.sh                     # test PKI in ./pki (gitignored): 4 CAs, server/client certs, CRL, Flower keys
SPIKE_DATA=<dir with sites/<site>/nasa_<site>.csv, hf-cache/> ./spike.sh
docker compose down
```

`spike.sh`: registers plant 1's Flower key, starts plant 1 (registered) and plant 2 (valid
certificate, unregistered key), probes the gateway from the "internet" (`probe.py`), runs one solar
training round for plant 1 through the gateway, then unregisters plant 1.

## Result (2026-11-19, laptop, Docker, CPU)

| Check | Result |
|---|---|
| Register plant key via TLS Control API (`flwr supernode register <pub> <app> <federation> --format json`) | ✅ returns `node-id` |
| Plant 1 online through tunnel → gateway → SuperLink with node auth | ✅ `status: online` |
| Plant 2: valid certificate, unregistered key | ✅ passes the gateway, refused by Flower: `No SuperNode found with the given public key` |
| No client certificate | ✅ refused by the gateway (HTTP 400 "No required SSL certificate was sent") |
| Revoked certificate (CRL) | ✅ refused (400 "The SSL certificate error") |
| Certificate from another CA | ✅ refused (400) |
| Control API path through the gateway with a valid certificate | ✅ 404 (only `/flwr.proto.Fleet/` is proxied) |
| SuperLink 9091/9092/9093 from the internet | ✅ not reachable |
| One solar training round through the gateway | ✅ `done`, W/m², 3.8 MB update, 109 gRPC calls, all through mTLS |
| Unregister plant 1 | ✅ cut off immediately (`Node ID … not found`); status `unregistered` |
| Register the same key again | ✅ refused ("already in use"): a re-issued kit needs new keys |
| Proxy cost | ~10 MB RAM per nginx |

## Findings that change the plan
1. **Flower 1.25 SuperNodes can't present a client certificate** (only `--root-certificates`), so every
   site kit needs a small **tunnel** container (nginx) that holds the plant certificate.
2. **Node auth needs TLS to the next hop**: the SuperNode refuses `--insecure` with a private key, so the
   tunnel listens with TLS and the SuperNode trusts a **plant-local CA** created at enrollment.
3. **nginx rejects bad clients with HTTP 400 after the TLS handshake**, not by failing the handshake.
   Nothing reaches Flower or the API either way; if a handshake-level failure is wanted, a proxy that
   aborts the handshake (e.g. HAProxy `verify required`, Envoy) can replace nginx later.
4. The Control API uses the same TLS certificates as the Fleet API, so the API's `flwr` CLI needs
   `root-certificates` in its federation config. ServerAppIo has no TLS in 1.25 and must stay internal.
5. An unregistered SuperNode keeps retrying; the site agent should detect this and show "revoked".
6. Not tested yet: 75 MB / 444 MB updates through the gateway (`client_max_body_size 1g` is set),
   certificate renewal while a run is active.
