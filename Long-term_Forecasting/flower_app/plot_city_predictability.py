"""
City Predictability Comparison
Shows why some cities are easier/harder to forecast at different horizons.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from statsmodels.tsa.stattools import acf
import os

# ============================================================
# LOAD DATA
# ============================================================
dataset_dir = '../datasets/custom'
cities = {
    'Taraz': 'nasa_taraz.csv',
    'Aktau': 'nasa_aktau.csv',
    'Almaty': 'nasa_almaty.csv',
    'Astana': 'nasa_astana.csv',
    'Aktobe': 'nasa_aktobe.csv',
}

data = {}
for city_name, filename in cities.items():
    filepath = os.path.join(dataset_dir, filename)
    # Skip the NASA header (first 21 lines), header is on line 22
    df = pd.read_csv(filepath, skiprows=21)
    data[city_name] = df['WS50M'].values
    print(f"{city_name}: {len(df)} samples")

# ============================================================
# CREATE FIGURE
# ============================================================
fig = plt.figure(figsize=(18, 12))
gs = fig.add_gridspec(3, 2, hspace=0.35, wspace=0.3)

# ============================================================
# TOP ROW: 2-week raw time series
# ============================================================
ax1 = fig.add_subplot(gs[0, :])

# Plot 2 weeks of data (336 hours * 2)
n_weeks = 2
n_samples = 336 * n_weeks

colors = {'Taraz': '#2E86AB', 'Aktau': '#A23B72', 'Almaty': '#F18F01', 'Astana': '#C73E1D', 'Aktobe': '#6A994E'}

for city_name, color in colors.items():
    ax1.plot(data[city_name][:n_samples], label=city_name, linewidth=1.5, alpha=0.8, color=color)

ax1.set_title('Wind Speed — Raw Signal Comparison (2 weeks)', fontsize=15, fontweight='bold', pad=15)
ax1.set_xlabel('Time (hours)', fontsize=12, fontweight='bold')
ax1.set_ylabel('Wind Speed at 10m (m/s)', fontsize=12, fontweight='bold')
ax1.legend(fontsize=11, loc='upper right', framealpha=0.95)
ax1.grid(alpha=0.3, linestyle='--')
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

# Add annotations for h=1 and h=72
ax1.text(0.02, 0.95, 'h=1: 1 hour ahead (short-term trends dominate)',
         transform=ax1.transAxes, fontsize=10, verticalalignment='top',
         bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
ax1.text(0.02, 0.85, 'h=72: 72 hours (3 days) ahead (periodic patterns matter)',
         transform=ax1.transAxes, fontsize=10, verticalalignment='top',
         bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.7))

# ============================================================
# MIDDLE ROW: ACF plots (Taraz vs Aktau)
# ============================================================
ax2 = fig.add_subplot(gs[1, 0])
ax3 = fig.add_subplot(gs[1, 1])

# Calculate ACF up to 500 lags (21 days)
nlags = 500
acf_taraz = acf(data['Taraz'], nlags=nlags, fft=False)
acf_aktau = acf(data['Aktau'], nlags=nlags, fft=False)

# Plot Taraz ACF
ax2.plot(acf_taraz, linewidth=2, color=colors['Taraz'], label='Taraz')
ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
ax2.axvline(x=1, color='blue', linestyle='--', linewidth=2, alpha=0.6, label='h=1 (short-term)')
ax2.axvline(x=72, color='red', linestyle='--', linewidth=2, alpha=0.6, label='h=72 (3 days)')
ax2.fill_between(range(nlags+1), 0, acf_taraz, alpha=0.2, color=colors['Taraz'])
ax2.set_title('Taraz — Autocorrelation (Predictable Signal)', fontsize=13, fontweight='bold', pad=10)
ax2.set_xlabel('Lag (hours)', fontsize=11, fontweight='bold')
ax2.set_ylabel('ACF', fontsize=11, fontweight='bold')
ax2.set_ylim(-0.3, 1.0)
ax2.legend(fontsize=10, loc='upper right')
ax2.grid(alpha=0.3, linestyle='--')
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)

# Annotate ACF values at key lags
acf_taraz_h1 = acf_taraz[1]
acf_taraz_h72 = acf_taraz[72]
ax2.text(1, acf_taraz_h1 + 0.05, f'{acf_taraz_h1:.3f}', ha='center', fontsize=9, fontweight='bold')
ax2.text(72, acf_taraz_h72 + 0.05, f'{acf_taraz_h72:.3f}', ha='center', fontsize=9, fontweight='bold')

# Plot Aktau ACF
ax3.plot(acf_aktau, linewidth=2, color=colors['Aktau'], label='Aktau')
ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
ax3.axvline(x=1, color='blue', linestyle='--', linewidth=2, alpha=0.6, label='h=1 (short-term)')
ax3.axvline(x=72, color='red', linestyle='--', linewidth=2, alpha=0.6, label='h=72 (3 days)')
ax3.fill_between(range(nlags+1), 0, acf_aktau, alpha=0.2, color=colors['Aktau'])
ax3.set_title('Aktau — Autocorrelation (Less Predictable)', fontsize=13, fontweight='bold', pad=10)
ax3.set_xlabel('Lag (hours)', fontsize=11, fontweight='bold')
ax3.set_ylabel('ACF', fontsize=11, fontweight='bold')
ax3.set_ylim(-0.3, 1.0)
ax3.legend(fontsize=10, loc='upper right')
ax3.grid(alpha=0.3, linestyle='--')
ax3.spines['top'].set_visible(False)
ax3.spines['right'].set_visible(False)

# Annotate ACF values at key lags
acf_aktau_h1 = acf_aktau[1]
acf_aktau_h72 = acf_aktau[72]
ax3.text(1, acf_aktau_h1 + 0.05, f'{acf_aktau_h1:.3f}', ha='center', fontsize=9, fontweight='bold')
ax3.text(72, acf_aktau_h72 + 0.05, f'{acf_aktau_h72:.3f}', ha='center', fontsize=9, fontweight='bold')

# ============================================================
# BOTTOM ROW: ACF for all cities
# ============================================================
ax4 = fig.add_subplot(gs[2, 0])

# ACF up to h=100 for all cities
nlags_short = 100
for city_name, color in colors.items():
    acf_vals = acf(data[city_name], nlags=nlags_short, fft=False)
    ax4.plot(acf_vals, label=city_name, linewidth=2, color=color, alpha=0.8)

ax4.axvline(x=1, color='blue', linestyle='--', linewidth=1.5, alpha=0.5)
ax4.axvline(x=72, color='red', linestyle='--', linewidth=1.5, alpha=0.5)
ax4.text(1, -0.22, 'h=1', ha='center', fontsize=9, color='blue', fontweight='bold')
ax4.text(72, -0.22, 'h=72', ha='center', fontsize=9, color='red', fontweight='bold')
ax4.set_title('All Cities — ACF Comparison (0–100 hour lags)', fontsize=13, fontweight='bold', pad=10)
ax4.set_xlabel('Lag (hours)', fontsize=11, fontweight='bold')
ax4.set_ylabel('Autocorrelation', fontsize=11, fontweight='bold')
ax4.legend(fontsize=10, loc='upper right')
ax4.grid(alpha=0.3, linestyle='--')
ax4.spines['top'].set_visible(False)
ax4.spines['right'].set_visible(False)
ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
ax4.set_ylim(-0.3, 1.0)

# ============================================================
# BOTTOM RIGHT: ACF statistics table
# ============================================================
ax5 = fig.add_subplot(gs[2, 1])
ax5.axis('off')

# Compute statistics
stats_data = []
for city_name in ['Taraz', 'Aktau', 'Almaty', 'Astana', 'Aktobe']:
    acf_vals = acf(data[city_name], nlags=500, fft=False)
    acf_h1 = acf_vals[1]
    acf_h72 = acf_vals[72]
    ratio = acf_h72 / acf_h1 if acf_h1 > 0 else 0
    stats_data.append([city_name, f'{acf_h1:.4f}', f'{acf_h72:.4f}', f'{ratio:.4f}'])

table = ax5.table(
    cellText=stats_data,
    colLabels=['City', 'ACF(h=1)', 'ACF(h=72)', 'Ratio (h=72/h=1)'],
    cellLoc='center',
    loc='center',
    bbox=[0, 0, 1, 1],
    colWidths=[0.25, 0.25, 0.25, 0.25]
)

table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1, 2.5)

# Style header
for i in range(4):
    table[(0, i)].set_facecolor('#2C3E50')
    table[(0, i)].set_text_props(weight='bold', color='white')

# Color rows by city
city_colors_light = {'Taraz': '#D4E6F1', 'Aktau': '#F5D5E8', 'Almaty': '#FCF5E5', 'Astana': '#FADBD8', 'Aktobe': '#D5F4E6'}
for i, city_name in enumerate(['Taraz', 'Aktau', 'Almaty', 'Astana', 'Aktobe'], 1):
    for j in range(4):
        table[(i, j)].set_facecolor(city_colors_light[city_name])

# Add interpretation text
interpretation = (
    "Interpretation:\n\n"
    "• High ACF(h=72): Signal has strong patterns at 72-hour lags → easier to predict 3 days out\n"
    "• Low ACF(h=72): Signal is noisy at that scale → harder to predict 3 days out\n"
    "• Taraz: Periodic wind cycles (daily + 3-day patterns) → consistent fairness\n"
    "• Aktau: Desert microbursts (random) → unfair at h=72 but fair at h=1"
)

ax5.text(0.5, -0.35, interpretation, transform=ax5.transAxes,
         fontsize=10, ha='center', va='top',
         bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8, pad=1))

# ============================================================
# MAIN TITLE
# ============================================================
fig.suptitle(
    'Wind Speed Predictability by City: Why Fairness Varies Across Forecast Horizons',
    fontsize=17, fontweight='bold', y=0.995
)

# ============================================================
# SAVE
# ============================================================
plt.savefig('./fig_city_predictability.png', dpi=200, bbox_inches='tight', facecolor='white')
print("\n✓ Saved: fig_city_predictability.png")
plt.close()

# ============================================================
# PRINT SUMMARY STATISTICS
# ============================================================
print("\n" + "="*70)
print("AUTOCORRELATION SUMMARY (ACF at key lags)")
print("="*70)
print(f"{'City':<12} {'ACF(h=1)':<12} {'ACF(h=72)':<12} {'h=72/h=1':<12} {'Interpretation':<25}")
print("-"*70)

for city_name in ['Taraz', 'Aktau', 'Almaty', 'Astana', 'Aktobe']:
    acf_vals = acf(data[city_name], nlags=500, fft=False)
    acf_h1 = acf_vals[1]
    acf_h72 = acf_vals[72]
    ratio = acf_h72 / acf_h1 if acf_h1 > 0 else 0

    if acf_h72 > 0.3:
        interp = "Predictable at h=72"
    elif acf_h72 > 0.1:
        interp = "Moderately predictable"
    else:
        interp = "Unpredictable at h=72"

    print(f"{city_name:<12} {acf_h1:<12.4f} {acf_h72:<12.4f} {ratio:<12.4f} {interp:<25}")

print("="*70)
