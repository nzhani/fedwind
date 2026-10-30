import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import csv
import pandas as pd
import os
from pathlib import Path

matplotlib.rcParams['font.family'] = 'DejaVu Sans'

# ============================================================
# HELPER: Load wind speed data from raw files
# ============================================================
def load_nasa_wind_speed(city_name):
    """Load WS50M (wind speed) from NASA POWER dataset CSV."""
    # Map city names in log to file names
    city_file_map = {
        'Almaty': 'almaty',
        'Zhezkazgan': 'zhezkazgan',
        'Aktau': 'aktau',
        'Taraz': 'taraz',
        'Aktobe': 'aktobe'
    }

    file_name = city_file_map.get(city_name)
    if not file_name:
        return None

    # Look in parent directory (Long-term_Forecasting/)
    script_dir = Path(__file__).resolve().parent
    parent_dir = script_dir.parent
    file_path = parent_dir / 'datasets' / 'custom' / f'nasa_{file_name}.csv'

    if not os.path.exists(file_path):
        return None

    try:
        # Read until "-END HEADER-"
        with open(file_path, 'r', errors='ignore') as f:
            lines = f.readlines()

        data_start_idx = None
        for i, line in enumerate(lines):
            if '-END HEADER-' in line:
                data_start_idx = i + 1
                break

        if data_start_idx is None:
            return None

        # Read with flexible delimiter
        df = pd.read_csv(
            file_path,
            skiprows=data_start_idx,
            sep=r'[,\t\s]+',
            engine='python'
        )

        # Normalize column names
        df.columns = [c.strip().upper().replace('\ufeff', '') for c in df.columns]

        # Get WS50M (50m wind speed)
        if 'WS50M' not in df.columns:
            return None

        # Clean fill values
        ws = df['WS50M'].replace(-999, np.nan)
        ws = ws.dropna()

        if len(ws) == 0:
            return None

        return float(ws.mean())
    except Exception as e:
        print(f"  Error loading NASA {city_name}: {e}")
        return None


def load_vnmet_wind_speed(station_id):
    """Load Vavg80 [m/s] (wind speed) from VNMET station CSV."""
    # Look in parent directory (Long-term_Forecasting/)
    script_dir = Path(__file__).resolve().parent
    parent_dir = script_dir.parent
    file_path = parent_dir / 'datasets' / 'VNMET' / f'{station_id:03d}.csv'

    if not os.path.exists(file_path):
        return None

    try:
        df = pd.read_csv(file_path)

        # Target column is "Vavg80 [m/s]"
        if 'Vavg80 [m/s]' not in df.columns:
            return None

        ws = df['Vavg80 [m/s]'].dropna()

        if len(ws) == 0:
            return None

        return float(ws.mean())
    except Exception as e:
        print(f"  Error loading VNMET {station_id}: {e}")
        return None


def compute_per_client_wind_speeds_nasa():
    """Compute mean wind speed for each NASA city client."""
    cities = ['Almaty', 'Zhezkazgan', 'Aktau', 'Taraz', 'Aktobe']
    wind_speeds = {}

    print("Loading NASA wind speed data per city:")
    for city in cities:
        ws = load_nasa_wind_speed(city)
        if ws is not None:
            wind_speeds[city] = ws
            print(f"  {city}: {ws:.4f} m/s")
        else:
            print(f"  {city}: Could not load")

    return wind_speeds


def compute_per_client_wind_speeds_vnmet():
    """Compute mean wind speed for each VNMET station client."""
    wind_speeds = {}

    print("Loading VNMET wind speed data per station:")
    for station_id in range(1, 6):  # 5 stations: 001-005
        ws = load_vnmet_wind_speed(station_id)
        if ws is not None:
            wind_speeds[f'Station_{station_id:03d}'] = ws
            print(f"  Station {station_id:03d}: {ws:.4f} m/s")
        else:
            print(f"  Station {station_id:03d}: Could not load")

    return wind_speeds

# ============================================================
# LOAD DATA
# ============================================================
rows = []
with open('./master_experiment_log.csv', 'r') as f:
    reader = csv.DictReader(f)
    for r in reader:
        cleaned = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in r.items()}
        rows.append(cleaned)

print(f"Loaded {len(rows)} experiments")

# Split by dataset
nasa_rows = [r for r in rows if r.get('dataset_name', '').strip() in ('', 'None')]
vnmet_rows = [r for r in rows if r.get('dataset_name', '').strip() == 'VNMET']
print(f"NASA: {len(nasa_rows)} experiments, VNMET: {len(vnmet_rows)} experiments")

# ============================================================
# HELPER: extract best experiment per model for a given horizon
# ============================================================
def get_best_per_model(data_rows, horizon, all_models, use_normalized=False,
                       per_client_wind_speeds=None, dataset_name='NASA'):
    """
    Extract best model per metric.
    If use_normalized=True and per_client_wind_speeds provided, normalize MAE by per-client mean wind speed.
    Formula: nMAE = MAE / mean(wind_speed_for_that_client)
    """
    best = {}
    for r in data_rows:
        if r['pred_len'] != str(horizon):
            continue
        m = r['model'].replace('_nonlinear', '').upper()
        if r['best_test_mae'] == '' or r['client_val_mae_min'] == '':
            continue
        mae = float(r['best_test_mae'])

        best_city = r['client_val_mae_best_city']
        worst_city = r['client_val_mae_worst_city']

        if m not in best or mae < best[m]['mae']:
            client_min = float(r['client_val_mae_min'])
            client_max = float(r['client_val_mae_max'])
            client_mean = float(r['client_val_mae_mean'])
            client_std = float(r['client_val_mae_std'])

            # Per-client normalization
            if use_normalized and per_client_wind_speeds:
                # Normalize by per-client mean wind speed
                # nMAE = MAE / mean(wind_speed)
                wind_best = per_client_wind_speeds.get(best_city)
                wind_worst = per_client_wind_speeds.get(worst_city)

                if wind_best and wind_worst:
                    # Recompute fairness ratio after per-client normalization
                    client_min_norm = client_min / wind_best
                    client_max_norm = client_max / wind_worst
                    client_mean_norm = client_mean / np.mean(list(per_client_wind_speeds.values()))
                    fairness_norm = client_max_norm / client_min_norm if client_min_norm > 0 else float('inf')
                    # If normalization reverses the ranking, swap so min_norm < max_norm
                    # and update city labels accordingly
                    if client_min_norm > client_max_norm:
                        client_min_norm, client_max_norm = client_max_norm, client_min_norm
                        best_city, worst_city = worst_city, best_city
                        fairness_norm = client_max_norm / client_min_norm if client_min_norm > 0 else float('inf')
                else:
                    # Fallback if wind data unavailable
                    client_min_norm = client_min
                    client_max_norm = client_max
                    client_mean_norm = client_mean
                    fairness_norm = float(r['fairness_ratio'])
            else:
                client_min_norm = client_min
                client_max_norm = client_max
                client_mean_norm = client_mean
                fairness_norm = float(r['fairness_ratio'])

            best[m] = {
                'mae': mae,
                'algo': r['fl_algorithm'],
                'client_min': client_min,
                'client_max': client_max,
                'client_mean': client_mean,
                'client_std': client_std,
                'client_min_norm': client_min_norm,
                'client_max_norm': client_max_norm,
                'client_mean_norm': client_mean_norm,
                'best_city': best_city,
                'worst_city': worst_city,
                'fairness': float(r['fairness_ratio']),
                'fairness_norm': fairness_norm,
            }
    models = [m for m in all_models if m in best]
    return best, models


# ============================================================
# HELPER: plot one row of 3 horizon panels
# ============================================================
def plot_fairness_row(fig, axes, dataset_rows, all_models, model_label_map, dataset_name,
                      use_normalized=False, per_client_wind_speeds=None):
    horizons = [1, 72, 432]
    horizon_titles = ['h=1 (1-hour forecast)', 'h=72 (3-day forecast)', 'h=432 (18-day forecast)']
    width = 0.25
    colors = {'min': '#57bb8a', 'mean': '#4f8fc6', 'max': '#d95c54'}

    for col, (h, title) in enumerate(zip(horizons, horizon_titles)):
        ax = axes[col]
        best, models = get_best_per_model(dataset_rows, h, all_models,
                                          use_normalized=use_normalized,
                                          per_client_wind_speeds=per_client_wind_speeds,
                                          dataset_name=dataset_name)

        if not models:
            ax.text(0.5, 0.5, f'No data for h={h}', transform=ax.transAxes,
                    ha='center', va='center', fontsize=13, color='gray')
            ax.set_title(title, fontsize=14, fontweight='bold', pad=10)
            continue

        labels = [model_label_map[m] for m in models]
        x = np.arange(len(models))

        # Use normalized values if requested
        if use_normalized:
            min_vals = [best[m]['client_min_norm'] for m in models]
            mean_vals = [best[m]['client_mean_norm'] for m in models]
            max_vals = [best[m]['client_max_norm'] for m in models]
            ylabel = f'Normalized MAE (nMAE = MAE / mean wind) per Client'
            fairness = [best[m]['fairness_norm'] for m in models]
        else:
            min_vals = [best[m]['client_min'] for m in models]
            mean_vals = [best[m]['client_mean'] for m in models]
            max_vals = [best[m]['client_max'] for m in models]
            ylabel = 'Validation MAE per Client'
            fairness = [best[m]['fairness'] for m in models]
        best_city = best[models[0]]['best_city']
        worst_city = best[models[0]]['worst_city']

        ax.bar(x - width, min_vals, width, label=f'Best Client ({best_city})',
               color=colors['min'], edgecolor='white', linewidth=1, zorder=3)
        ax.bar(x, mean_vals, width, label='Mean (all clients)',
               color=colors['mean'], edgecolor='white', linewidth=1, zorder=3)
        ax.bar(x + width, max_vals, width, label=f'Worst Client ({worst_city})',
               color=colors['max'], edgecolor='white', linewidth=1, zorder=3)

        # Fairness ratio annotations
        for i, f in enumerate(fairness):
            ax.text(i, max_vals[i] + (max(max_vals) - min(min_vals)) * 0.04,
                    f'×{f:.2f}', ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='#2C3E50')

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=11)
        ax.set_title(title, fontsize=14, fontweight='bold', pad=10)
        ax.legend(fontsize=9, loc='upper left', framealpha=0.9)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', alpha=0.3, linestyle='--', zorder=0)
        ax.tick_params(axis='y', labelsize=11)

        # Smart y-axis limits
        data_min = min(min_vals)
        data_max = max(max_vals)
        data_range = data_max - data_min
        margin = data_range * 0.35

        # Zoom in when the spread between bars is small relative to the values.
        # This happens at h=72/432 in both raw and normalized plots.
        # Without zooming, bars look identical because differences are <30% of max.
        if data_range / data_max < 0.4 and data_min > 0:
            ax.set_ylim(data_min - margin * 1.5, data_max + margin)
        else:
            ax.set_ylim(0, data_max + margin)

        if col == 0:
            ax.set_ylabel(ylabel, fontsize=13, fontweight='bold')

        # Print summary
        for m in models:
            d = best[m]
            if use_normalized:
                print(f"  {dataset_name} h={h} {m}: nMAE min={d['client_min_norm']:.4f} ({d['best_city']})  "
                      f"mean={d['client_mean_norm']:.4f}  max={d['client_max_norm']:.4f} ({d['worst_city']})  "
                      f"fairness_raw={d['fairness']:.4f}  fairness_norm={d['fairness_norm']:.4f}  algo={d['algo']}")
            else:
                print(f"  {dataset_name} h={h} {m}: min={d['client_min']:.4f} ({d['best_city']})  "
                      f"mean={d['client_mean']:.4f}  max={d['client_max']:.4f} ({d['worst_city']})  "
                      f"fairness={d['fairness']:.4f}  algo={d['algo']}")


# ============================================================
# MODEL CONFIG
# ============================================================
all_models = ['GPT4TS', 'BERT', 'BART', 'LLAMA']
model_label_map = {
    'GPT4TS': 'GPT4TS',
    'BERT': 'BERT',
    'BART': 'BART',
    'LLAMA': 'LLaMA'
}

# ============================================================
# Load per-client wind speed data for normalization
# ============================================================
print(f"\n=== Loading per-client wind speed data ===")
nasa_wind_speeds = compute_per_client_wind_speeds_nasa()
vnmet_wind_speeds = compute_per_client_wind_speeds_vnmet()

# ============================================================
# FIGURE 1: NASA — Raw MAE
# ============================================================
print("\n=== NASA Dataset (Raw MAE) ===")
fig1, axes1 = plt.subplots(1, 3, figsize=(20, 7))
plot_fairness_row(fig1, axes1, nasa_rows, all_models, model_label_map, 'NASA',
                  use_normalized=False)
fig1.suptitle('Per-Client Fairness — NASA Wind Dataset (5 Kazakhstan Cities)',
              fontsize=16, fontweight='bold', y=1.02)
plt.tight_layout()
fig1.savefig('./fig2a_fairness_nasa.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close(fig1)
print("Saved: fig2a_fairness_nasa.png")

# ============================================================
# FIGURE 2: VNMET — Raw MAE
# ============================================================
print("\n=== VNMET Dataset (Raw MAE) ===")
fig2, axes2 = plt.subplots(1, 3, figsize=(20, 7))
plot_fairness_row(fig2, axes2, vnmet_rows, all_models, model_label_map, 'VNMET',
                  use_normalized=False)
fig2.suptitle('Per-Client Fairness — VNMET Wind Dataset (5 Stations)',
              fontsize=16, fontweight='bold', y=1.02)
plt.tight_layout()
fig2.savefig('./fig2b_fairness_vnmet.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close(fig2)
print("Saved: fig2b_fairness_vnmet.png")

# ============================================================
# FIGURE 3: NASA — Normalized MAE (per-client wind speed)
# ============================================================
if nasa_wind_speeds:
    print(f"\n=== NASA Dataset (Per-Client Normalized MAE) ===")
    fig3, axes3 = plt.subplots(1, 3, figsize=(20, 7))
    plot_fairness_row(fig3, axes3, nasa_rows, all_models, model_label_map, 'NASA',
                      use_normalized=True, per_client_wind_speeds=nasa_wind_speeds)
    fig3.suptitle('Per-Client Fairness (Normalized: nMAE = MAE / mean wind speed) — NASA Wind Dataset',
                  fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    fig3.savefig('./fig2a_fairness_nasa_normalized.png', dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig3)
    print("Saved: fig2a_fairness_nasa_normalized.png")
else:
    print("Skipping NASA normalized plot (no wind speed data)")

# ============================================================
# FIGURE 4: VNMET — Normalized MAE (per-client wind speed)
# ============================================================
if vnmet_wind_speeds:
    print(f"\n=== VNMET Dataset (Per-Client Normalized MAE) ===")
    fig4, axes4 = plt.subplots(1, 3, figsize=(20, 7))
    plot_fairness_row(fig4, axes4, vnmet_rows, all_models, model_label_map, 'VNMET',
                      use_normalized=True, per_client_wind_speeds=vnmet_wind_speeds)
    fig4.suptitle('Per-Client Fairness (Normalized: nMAE = MAE / mean wind speed) — VNMET Wind Dataset',
                  fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    fig4.savefig('./fig2b_fairness_vnmet_normalized.png', dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig4)
    print("Saved: fig2b_fairness_vnmet_normalized.png")
else:
    print("Skipping VNMET normalized plot (no wind speed data)")

# ============================================================
# LOAD DATA
# ============================================================
rows = []
with open('./master_experiment_log.csv', 'r') as f:
    reader = csv.DictReader(f)
    for r in reader:
        cleaned = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in r.items()}
        rows.append(cleaned)

# Filter to NASA-only (experiments without dataset_name or with empty dataset_name)
rows = [r for r in rows if r.get('dataset_name', '').strip() in ('', 'None')]

print(f"Loaded {len(rows)} experiments (NASA only)")

# ============================================================
# FIGURE 1: Convergence Rate — EXTRACTED FROM DATA
# ============================================================

strategies_order = ['fedavg', 'fedprox', 'fedln', 'fedper']
strategy_labels = ['FedAvg', 'FedProx', 'FedLN', 'FedPer']

convergence_stats = {}
for algo in strategies_order:
    exps = [r for r in rows if r['fl_algorithm'] == algo]
    dec = sum(1 for r in exps if r['loss_trend_last3'] == 'decreasing')
    inc = sum(1 for r in exps if r['loss_trend_last3'] == 'increasing')
    total = len(exps)
    pct = dec / total * 100 if total > 0 else 0
    convergence_stats[algo] = {'decreasing': dec, 'total': total, 'pct': pct}
    print(f"  {algo:<10}: {dec}/{total} decreasing ({pct:.1f}%)")

decreasing = [convergence_stats[a]['decreasing'] for a in strategies_order]
totals = [convergence_stats[a]['total'] for a in strategies_order]
pcts = [convergence_stats[a]['pct'] for a in strategies_order]

fig, ax = plt.subplots(figsize=(10, 6))

colors = ['#d95c54', '#57bb8a', '#f3c78b', '#eda17a']
bars = ax.bar(strategy_labels, pcts, color=colors, width=0.6, edgecolor='white', linewidth=1.5, zorder=3)

for bar, d, t, p in zip(bars, decreasing, totals, pcts):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
            f'{p:.1f}%', ha='center', va='bottom', fontsize=18, fontweight='bold',
            color=bar.get_facecolor())
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height()/2,
            f'{d}/{t}', ha='center', va='center', fontsize=14, fontweight='bold',
            color='white')

ax.set_ylabel('Experiments with Decreasing Val Loss (%)', fontsize=13, fontweight='bold')
ax.set_title('Convergence Success Rate by FL Strategy\n',
             fontsize=15, fontweight='bold', pad=10)

max_pct = max(pcts)
ax.set_ylim(0, max_pct + 20)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_linewidth(0.5)
ax.spines['bottom'].set_linewidth(0.5)
ax.tick_params(axis='both', labelsize=13)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0f}%'))
ax.grid(axis='y', alpha=0.3, linestyle='--', zorder=0)

# Find the best strategy dynamically
best_algo_idx = np.argmax(pcts)
worst_algo_idx = np.argmin(pcts)
ratio = pcts[best_algo_idx] / pcts[worst_algo_idx] if pcts[worst_algo_idx] > 0 else float('inf')

ax.annotate(f'{strategy_labels[best_algo_idx]} achieves {ratio:.0f}× higher\nconvergence rate than {strategy_labels[worst_algo_idx]}',
            xy=(best_algo_idx, pcts[best_algo_idx] + 2), xytext=(best_algo_idx + 1.3, pcts[best_algo_idx] + 12),
            fontsize=11, style='italic', color='#2C3E50',
            arrowprops=dict(arrowstyle='->', color='#2C3E50', lw=1.5),
            ha='center')

plt.tight_layout()
plt.savefig('./fig1_convergence_rate.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close()
print("Figure 1 saved")
