# After the kit is installed: from new plant to federated round

For the live plant **Turkistan Solar**, after it was registered (window B), approved (window A) and
its kit downloaded. The existing plant **Kyzylorda Solar** (`kyzylorda-solar-0ebd`) is already
online and joined. Run every command in one terminal.

---

## 0. Install the kit (the command that comes just before)

```bash
export FEDWIND_DATA=$HOME/fedwind-demo-data
TS=$(basename ~/Downloads/fedwind-site-turkistan-solar-*.zip .zip | sed 's/^fedwind-site-//'); echo $TS
SIM_INBOX=~/fedwind/deploy/sim/exports/turkistan_solar_2024.csv ~/fedwind/deploy/sim/run_site.sh ~/Downloads/fedwind-site-$TS.zip
```

## 1. Wait until the plant is Online (about 1 minute)

Window B → **Your plants → Turkistan Solar**. The activity list shows **Kit installed**, then the
status turns **Online**.

> "The kit created its own keys, proved who it is with a one-time token, and received its
> certificate. From now on it reports its status every 30 seconds."

If it stays offline for more than 2 minutes:

```bash
docker logs --tail 30 fedwind-site-$TS-agent-1
```

## 2. Show that the keys stay on the plant

```bash
ls -l ~/fedwind/deploy/sim/sites/$TS/secrets/
```

> "These private keys exist only on the plant's machine. The platform receives status and
> data-quality counts, never the measurements."

## 3. Show the plant page

On the plant page, point to:

- **Online** and the last heartbeat
- **Data quality**: valid hours, gaps
- **Training data**: 8784 hours, enough to train (the minimum is 2160)

## 4. Join the plant to training

```bash
~/fedwind/deploy/sim/join_training.sh $TS
```

Expected: `turkistan-solar-…: solar plant, training store 8784 hours` and
`can be selected for training runs`.

If it says *training store isn't there yet*, wait a minute and run it again.

> "Now the plant's federated-learning client starts. It can read only this plant's own data."

## 5. Memory safety (do not skip; the laptop crashed without it)

```bash
docker update --memory 4g --memory-swap 4g fedwind-site-kyzylorda-solar-0ebd-supernode fedwind-site-$TS-supernode
```

Repeat it after every `join_training.sh`, because joining recreates the container.

## 6. Start the federated run

Window A → **Experiments → solar**:

1. Tick **only Turkistan Solar and Kyzylorda Solar**.
2. Change these from the defaults:

   | Setting | Value |
   |---|---|
   | Rounds | **2** |
   | Local epochs | **1** (default is 2) |
   | Horizon | **1 h** |
   | Data | **5 %** (default is 100: this crashed the laptop) |
   | Min clients | **2** |

3. Click **Start**, then open the run page.

If Start says *a run is still running*, stop the old run on its run page first.

## 7. Watch the rounds

On the run page: in each round both plants show **replied**, with their training loss and error.

> "In each round the server sends the current model, about half a megabyte. Each plant trains on
> its own data and sends back only the updated weights. The server checks every update, rejects
> broken or suspicious ones, and averages the rest. Here both plants replied, and the error falls."

**If it is slow or fails:** open the finished run in another tab and say
*"This is a finished run with five sites; the live one shows the same."*

```
localhost:3000/training/solar-fedavg-h72-20261119T150357Z
```

## 8. Use the result for forecasts

When the run is **done**: **Promote** on the run page → **Forecast → solar → Turkistan Solar**.

> "With one click, the model the plants trained together serves forecasts. Each plant gets its
> own forecast from the shared model, and solar power is zero at night."

---

## After a rehearsal: remove Turkistan, keep Kyzylorda

```bash
~/fedwind/deploy/sim/join_training.sh $TS --leave
~/fedwind/deploy/sim/stop_site.sh $TS --forget
rm ~/Downloads/fedwind-site-turkistan-solar-*.zip
```

Then window A → **Plants** → Turkistan Solar → **Revoke**, so the live registration starts fresh.
