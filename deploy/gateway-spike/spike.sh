#!/usr/bin/env bash
# M0 spike driver: register a plant's Flower key over the TLS Control API, connect two plants through
# the mTLS gateway (one registered, one not), probe the gateway, run one training round, then
# unregister the plant and check it is cut off.
#
#   SPIKE_DATA=/path/with/sites+hf-cache ./spike.sh
set -euo pipefail
cd "$(dirname "$0")"
: "${SPIKE_DATA:?set SPIKE_DATA to a folder with sites/<site>/nasa_<site>.csv and hf-cache/}"
mkdir -p "$SPIKE_DATA/runs"
dc() { docker compose "$@"; }
admin() { dc exec -T admin bash -lc "$1"; }
step() { printf '\n=== %s\n' "$*"; }

step "start central side, gateway, plant tunnels, admin, prober"
dc up -d superlink gateway tunnel-site1 tunnel-site2 admin prober
sleep 6
dc logs superlink 2>&1 | grep -E "Fleet API|Control API|authentication|ERROR" | head -5 || true

step "admin: Flower app with a TLS federation to the Control API"
admin 'rm -rf /work && mkdir -p /work && cp -r /src/flower_app /work/app && cp /certs/internal-ca.crt /work/app/
cat >> /work/app/pyproject.toml <<EOF

[tool.flwr.federations.spike]
address = "superlink:9093"
root-certificates = "internal-ca.crt"
EOF
cat > /work/run.toml <<EOF
energy-type = "solar"
dataset-name = "KZSOLAR"
target-column = "KSTAR"
solar-target = "kstar"
daylight-mask = true
site-names = "konaev"
partition-sites = "almaty,zhezkazgan,aktau,taraz,aktobe,konaev,shymkent,kyzylorda,saran,turkistan"
num-clients = 1
num-server-rounds = 1
local-epochs = 1
fraction-train = 1.0
min-train-clients = 1
round-timeout = 900.0
pred-len = 24
seq-len = 48
llm-layers = 1
model = "gpt4ts_linear"
data-percent = 5
batch-size = 64
runs-dir = "/runs"
run-id = "spike-1"
save-predictions = false
EOF
echo ok'

step "register plant 1's Flower public key (plant 2 stays unregistered)"
REG=$(admin 'flwr supernode register /keys/flower-site1.pub /work/app spike --format json')
echo "$REG"
NODE_ID=$(python3 -c 'import json,sys,re; t=sys.argv[1]; m=re.search(r"\{.*\}", t, re.S); d=json.loads(m.group(0)); print(d.get("node-id") or d.get("node_id") or "")' "$REG")
echo "node id: $NODE_ID"

step "start both plants' SuperNodes"
dc up -d supernode-site1 supernode-site2
sleep 15
admin 'flwr supernode list /work/app spike --format json' | head -40

step "plant 2 (unregistered key) must be refused"
dc logs supernode-site2 2>&1 | grep -i -E "auth|denied|unauthenticated|permission|refused|error" | head -5 || true

step "probe the gateway from the internet"
dc exec -T prober python /probe.py

step "one training round through the gateway (plant 1)"
RUN=$(admin 'flwr run /work/app spike --run-config /work/run.toml --format json')
echo "$RUN" | tail -5
for i in $(seq 1 60); do
  [ -f "$SPIKE_DATA/runs/spike-1/result.json" ] && break
  sleep 10
done
python3 - "$SPIKE_DATA/runs/spike-1" <<'EOF'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
r = json.loads((d / "result.json").read_text()) if (d / "result.json").exists() else None
print("result:", None if r is None else {k: r.get(k) for k in ("status", "error", "unit", "energy_type", "best_round")})
for line in (d / "metrics.jsonl").read_text().splitlines() if (d / "metrics.jsonl").exists() else []:
    m = json.loads(line)
    print("round", m["round"], "clients", [(c["site"], c["status"]) for c in m["clients"]], "uplink", m.get("uplink_bytes"))
EOF
dc logs gateway 2>&1 | grep -E 'flwr.proto.Fleet' | awk '{print $2, $3, $4, $5, $6, $7}' | sort | uniq -c | head -8

step "unregister plant 1: it must be cut off"
admin "flwr supernode unregister $NODE_ID /work/app spike"
sleep 15
dc logs --since 20s supernode-site1 2>&1 | grep -i -E "auth|denied|unauthenticated|permission|error|exit" | head -5 || true
admin 'flwr supernode list /work/app spike --format json' | head -20
