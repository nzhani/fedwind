#!/usr/bin/env python3
"""
============================================================================
Federated Learning Client Fairness — Root Cause Analysis
============================================================================

Purpose:
    Identify WHY certain clients (cities/stations) consistently achieve
    better or worse prediction accuracy in federated wind speed forecasting.
    
    Key question: Why is Taraz always the best and Aktau always the worst?

Approach:
    We analyze the raw wind speed data for each client to find statistical
    properties that explain predictability differences:
    
    1. DESCRIPTIVE STATISTICS — mean, std, CV, skewness, kurtosis
    2. DISTRIBUTION ANALYSIS — histograms, KDE, normality tests
    3. STATIONARITY — Augmented Dickey-Fuller (ADF) test
    4. AUTOCORRELATION — ACF/PACF (how "self-predictable" is the signal?)
    5. ROLLING VOLATILITY — local variance over sliding windows
    6. SEASONAL DECOMPOSITION — trend + seasonal + residual (STL)
    7. FREQUENCY SPECTRUM — FFT to identify dominant periodicities
    8. EXTREME VALUE ANALYSIS — tail behavior, outlier frequency
    9. CROSS-CLIENT COMPARISON — side-by-side summary dashboard
    10. PREDICTABILITY INDEX — composite score explaining FL fairness

Output:
    All figures saved to ./fairness_analysis/ (created automatically)

Author: Generated for Miras's FL research project
============================================================================
"""

import os
import sys
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator
from scipy import stats, signal
from scipy.fft import fft, fftfreq
from statsmodels.tsa.stattools import adfuller, acf, pacf
from statsmodels.tsa.seasonal import STL
from statsmodels.stats.diagnostic import acorr_ljungbox

warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================
BASE_DIR = "/raid/tin_trungchau/federated_learning/Long-term_Forecasting/datasets"
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fairness_analysis"
)

NASA_DIR = os.path.join(BASE_DIR, "custom")
VNMET_DIR = os.path.join(BASE_DIR, "VNMET")

NASA_TARGET = "WS50M"
VNMET_TARGET = "Vavg80 [m/s]"

NASA_SAMPLES_PER_HOUR = 1
VNMET_SAMPLES_PER_HOUR = 6  # 10-min sampling

NASA_STL_PERIOD = 24 * NASA_SAMPLES_PER_HOUR
VNMET_STL_PERIOD = 24 * VNMET_SAMPLES_PER_HOUR

NASA_FILES = {
    "Aktau":      "nasa_aktau.csv",
    "Almaty":     "nasa_almaty.csv",
    "Aktobe":     "nasa_aktobe.csv",
    "Taraz":      "nasa_taraz.csv",
    "Zhezkazgan": "nasa_zhezkazgan.csv",
}

VNMET_FILES = {
    "Station 001": "001.csv",
    "Station 002": "002.csv",
    "Station 003": "003.csv",
    "Station 004": "004.csv",
    "Station 005": "005.csv",
}

# Plot styling
plt.rcParams.update({
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.grid': True,
    'grid.alpha': 0.3,
    'font.size': 11,
    'axes.titlesize': 13,
    'axes.labelsize': 11,
    'figure.dpi': 150,
    'savefig.dpi': 200,
    'savefig.facecolor': 'white',
})

# Color palettes
NASA_COLORS = {
    "Aktau": "#e74c3c",       # red (worst)
    "Aktobe": "#e67e22",      # orange
    "Almaty": "#f1c40f",      # yellow
    "Astana": "#3498db",      # blue
    "Taraz": "#2ecc71",       # green (best)
    "Zhezkazgan": "#9b59b6",  # purple
}
VNMET_COLORS = {
    "Station 001": "#e74c3c",
    "Station 002": "#3498db",
    "Station 003": "#2ecc71",
    "Station 004": "#e67e22",
    "Station 005": "#9b59b6",
}


# ============================================================================
# DATA LOADING
# ============================================================================
def load_nasa(city_name, filename):
    """
    Load NASA POWER dataset.
    Format: header rows ending with '-END HEADER-', then YEAR MO DY HR columns.
    Fill value -999 is replaced with NaN and interpolated.
    """
    filepath = os.path.join(NASA_DIR, filename)
    
    # Find header end
    with open(filepath, 'r', errors='ignore') as f:
        lines = f.readlines()
    
    data_start = 0
    for i, line in enumerate(lines):
        if '-END HEADER-' in line:
            data_start = i + 1
            break
    
    df = pd.read_csv(filepath, skiprows=data_start, sep=r'[,\t\s]+', engine='python')
    df.columns = [c.strip().upper().replace('\ufeff', '') for c in df.columns]
    
    # Build datetime
    df['date'] = pd.to_datetime(
        df[['YEAR', 'MO', 'DY', 'HR']].rename(
            columns={'MO': 'MONTH', 'DY': 'DAY', 'HR': 'HOUR'}
        )
    )
    df = df.drop(columns=['YEAR', 'MO', 'DY', 'HR'])
    
    # Clean fill values
    df = df.replace(-999, np.nan)
    target_col = NASA_TARGET.upper()
    if target_col not in df.columns:
        raise KeyError(f"Target '{target_col}' not in {df.columns.tolist()}")
    
    df[target_col] = pd.to_numeric(df[target_col], errors='coerce')
    df[target_col] = df[target_col].interpolate(method='linear', limit_direction='both')
    
    df = df.set_index('date').sort_index()
    series = df[target_col].dropna()
    
    print(f"  [NASA] {city_name:12s}: {len(series):,} samples, "
          f"{series.index.min().date()} to {series.index.max().date()}")
    return series


def load_vnmet(station_name, filename):
    """
    Load VNMET dataset. Has 'date' column (or similar) + target column.
    """
    filepath = os.path.join(VNMET_DIR, filename)
    df = pd.read_csv(filepath)
    
    # Find date column
    date_col = None
    for col in df.columns:
        if col.strip().lower().replace(' ', '').replace('_', '') in ('date', 'datetime', 'timestamp'):
            date_col = col
            break
    if date_col is None:
        # Try first column
        date_col = df.columns[0]
    
    df['date'] = pd.to_datetime(df[date_col], errors='coerce')
    
    if VNMET_TARGET not in df.columns:
        raise KeyError(f"Target '{VNMET_TARGET}' not in {df.columns.tolist()}")
    
    df[VNMET_TARGET] = pd.to_numeric(df[VNMET_TARGET], errors='coerce')
    df = df.set_index('date').sort_index()
    series = df[VNMET_TARGET].dropna()
    
    print(f"  [VNMET] {station_name:12s}: {len(series):,} samples, "
          f"{series.index.min().date()} to {series.index.max().date()}")
    return series


# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def compute_descriptive_stats(series):
    """
    Basic descriptive statistics + distribution shape metrics.
    
    Coefficient of Variation (CV) = σ / μ
        Higher CV → more relative variability → harder to predict
    
    Skewness: asymmetry of distribution
        Positive skew → long right tail (occasional high winds)
    
    Kurtosis (excess): tail heaviness relative to normal
        High kurtosis → more extreme outliers → harder to predict
    """
    return {
        'n_samples': len(series),
        'mean': series.mean(),
        'std': series.std(),
        'cv': series.std() / series.mean() if series.mean() != 0 else np.inf,
        'median': series.median(),
        'min': series.min(),
        'max': series.max(),
        'range': series.max() - series.min(),
        'iqr': series.quantile(0.75) - series.quantile(0.25),
        'skewness': stats.skew(series.values),
        'kurtosis': stats.kurtosis(series.values),  # excess kurtosis
        'p5': series.quantile(0.05),
        'p95': series.quantile(0.95),
    }


def adf_test(series):
    """
    Augmented Dickey-Fuller (ADF) test for stationarity.
    
    H0: Unit root exists (series is non-stationary)
    H1: No unit root (series is stationary)
    
    If p-value < 0.05 → reject H0 → series IS stationary.
    More stationary → more predictable temporal patterns.
    
    ADF statistic: more negative = stronger evidence of stationarity.
    """
    # Use a subsample if series is very long (ADF is O(n²))
    s = series.values
    if len(s) > 50000:
        s = s[:50000]
    
    result = adfuller(s, maxlag=48, autolag='AIC')
    return {
        'adf_statistic': result[0],
        'adf_pvalue': result[1],
        'adf_lags_used': result[2],
        'adf_nobs': result[3],
        'adf_critical_1pct': result[4]['1%'],
        'adf_critical_5pct': result[4]['5%'],
        'adf_stationary': result[1] < 0.05,
    }


def autocorrelation_analysis(series, samples_per_hour=1):
    """
    ACF (Autocorrelation Function) and PACF analysis.
    
    ACF at lag k = Corr(y_t, y_{t-k})
        High ACF at small lags → strong short-term predictability.
        Slow ACF decay → long memory → easier to forecast.
    
    PACF at lag k = partial correlation after removing intermediate lags.
        Identifies the "direct" influence of lag k.
    
    We compute:
    - ACF decay rate: how quickly autocorrelation drops below 0.5
    - Lag-1 ACF: immediate predictability
    - Mean ACF (lags 1-24): average short-term predictability
    - Ljung-Box test: are autocorrelations jointly significant?
    
    nlags=168 hours covers one full week of hourly data.
    """
    s = series.values
    if len(s) > 50000:
        s = s[:50000]
    
    nlags = 168 * samples_per_hour
    lag1 = 1 * samples_per_hour
    lag24 = 24 * samples_per_hour
    lag168 = 168 * samples_per_hour

    acf_vals = acf(s, nlags=nlags, fft=True)
    pacf_vals = pacf(s, nlags=min(nlags, len(s) // 2 - 1), method='ywm')
    
    # ACF decay: first lag where ACF < 0.5
    decay_lag = nlags
    for i in range(1, len(acf_vals)):
        if acf_vals[i] < 0.5:
            decay_lag = i
            break
    
    # Ljung-Box test (are autocorrelations significant?)
    lb_result = acorr_ljungbox(s, lags=[lag24], return_df=True)
    
    return {
        'acf_values': acf_vals,
        'pacf_values': pacf_vals,
        'acf_lag1': acf_vals[lag1] if len(acf_vals) > lag1 else 0,
        'acf_lag24': acf_vals[lag24] if len(acf_vals) > lag24 else 0,
        'acf_mean_1_24': np.mean(acf_vals[lag1:min(lag24 + 1, len(acf_vals))]),
        'acf_mean_1_168': np.mean(acf_vals[lag1:min(lag168 + 1, len(acf_vals))]),
        'acf_decay_lag': decay_lag,
        'ljungbox_pvalue': lb_result['lb_pvalue'].values[0],
    }


def rolling_volatility(series, samples_per_hour=1):
    """
    Rolling standard deviation over different window sizes.
    
    Window sizes (hourly data):
        24h  = daily volatility
        168h = weekly volatility  
        720h = monthly volatility
    
    High volatility variability → regime changes → harder to predict.
    Stable volatility → consistent patterns → easier to predict.
    
    We measure the CV of rolling volatility itself:
        CV(σ_rolling) = std(σ_rolling) / mean(σ_rolling)
        Higher → more volatile volatility → harder to predict
    """
    results = {}
    windows_hours = [24, 168, 720]
    windows_steps = [h * samples_per_hour for h in windows_hours]
    for h, w in zip(windows_hours, windows_steps):
        if len(series) < w:
            continue
        rolling_std = series.rolling(window=w, min_periods=w // 2).std().dropna()
        results[f'vol_{h}h_mean'] = rolling_std.mean()
        results[f'vol_{h}h_std'] = rolling_std.std()
        results[f'vol_{h}h_cv'] = rolling_std.std() / rolling_std.mean() if rolling_std.mean() > 0 else np.inf
        results[f'vol_{h}h_series'] = rolling_std
    return results


def seasonal_decomposition(series, period=24):
    """
    STL (Seasonal and Trend decomposition using Loess).
    
    Decomposes series into: Y_t = T_t + S_t + R_t
        T_t = Trend (long-term direction)
        S_t = Seasonal (repeating pattern, period in samples)
        R_t = Residual (unpredictable component)
    
    Key metric: Residual-to-Total variance ratio
        Var(R) / Var(Y) → fraction of variance that's "unpredictable"
        Lower ratio → more variance explained by trend + season → easier to predict
    
    Also: Seasonal strength = 1 - Var(R) / Var(S + R)
        Closer to 1 → stronger seasonal pattern → more predictable
    """
    s = series.values
    # STL needs at least 2 full periods
    if len(s) < period * 2:
        return None
    
    # Subsample if too long (STL is memory-intensive)
    if len(s) > 100000:
        s = s[:100000]
        idx = series.index[:100000]
    else:
        idx = series.index[:len(s)]
    
    stl = STL(pd.Series(s, index=idx), period=period, robust=True)
    result = stl.fit()
    
    var_total = np.var(s)
    var_resid = np.var(result.resid)
    var_seasonal = np.var(result.seasonal)
    var_trend = np.var(result.trend)
    
    # Seasonal strength (Wang et al., 2006)
    seasonal_plus_resid_var = np.var(result.seasonal + result.resid)
    seasonal_strength = max(0, 1 - var_resid / seasonal_plus_resid_var) if seasonal_plus_resid_var > 0 else 0
    
    # Trend strength
    trend_plus_resid_var = np.var(result.trend + result.resid)
    trend_strength = max(0, 1 - var_resid / trend_plus_resid_var) if trend_plus_resid_var > 0 else 0
    
    return {
        'stl_result': result,
        'var_total': var_total,
        'var_trend': var_trend,
        'var_seasonal': var_seasonal,
        'var_resid': var_resid,
        'residual_ratio': var_resid / var_total if var_total > 0 else 1.0,
        'seasonal_strength': seasonal_strength,
        'trend_strength': trend_strength,
        'trend_pct': var_trend / var_total * 100,
        'seasonal_pct': var_seasonal / var_total * 100,
        'residual_pct': var_resid / var_total * 100,
    }


def frequency_analysis(series, samples_per_hour=1.0):
    """
    FFT (Fast Fourier Transform) to identify dominant periodicities.
    
    The FFT converts time-domain signal → frequency-domain.
    Peaks in the power spectrum indicate dominant cycles.
    
    Expected peaks for wind speed:
        24h  (diurnal cycle — solar heating)
        12h  (semi-diurnal — pressure oscillations)
        168h (weekly — may appear due to anthropogenic effects)
        8760h (annual — seasonal variation)
    
    We measure:
    - Spectral entropy: how "spread out" is energy across frequencies?
        Low entropy → energy concentrated in few frequencies → predictable
        High entropy → energy spread uniformly → noisy, hard to predict
    
    - Dominant frequency and its power fraction
    
    samples_per_hour: samples per hour (1.0 for hourly data)
    """
    s = series.values
    if len(s) > 100000:
        s = s[:100000]
    
    n = len(s)
    # Remove mean (DC component)
    s_centered = s - np.mean(s)
    
    # Apply Hann window to reduce spectral leakage
    window = np.hanning(n)
    s_windowed = s_centered * window
    
    # FFT
    yf = fft(s_windowed)
    xf = fftfreq(n, d=1.0 / samples_per_hour)
    
    # Power spectrum (one-sided)
    positive_mask = xf > 0
    freqs = xf[positive_mask]
    power = 2.0 / n * np.abs(yf[positive_mask]) ** 2
    
    # Convert to periods (hours)
    periods = 1.0 / freqs
    
    # Spectral entropy (normalized)
    power_norm = power / power.sum() if power.sum() > 0 else power
    power_norm = power_norm[power_norm > 0]  # avoid log(0)
    spectral_entropy = -np.sum(power_norm * np.log2(power_norm)) / np.log2(len(power_norm)) if len(power_norm) > 1 else 1.0
    
    # Top 5 dominant periods
    top_indices = np.argsort(power)[::-1][:10]
    dominant_periods = [(periods[i], power[i]) for i in top_indices if periods[i] < len(s)]
    
    # Power fraction in known cycles
    def band_power(center_period, bandwidth_frac=0.1):
        """Power within ±bandwidth_frac of center_period."""
        low = center_period * (1 - bandwidth_frac)
        high = center_period * (1 + bandwidth_frac)
        mask = (periods >= low) & (periods <= high)
        return power[mask].sum() / power.sum() if power.sum() > 0 else 0
    
    return {
        'freqs': freqs,
        'power': power,
        'periods': periods,
        'spectral_entropy': spectral_entropy,
        'dominant_periods': dominant_periods[:5],
        'diurnal_power_frac': band_power(24),
        'semidiurnal_power_frac': band_power(12),
        'weekly_power_frac': band_power(168),
    }


def extreme_value_analysis(series):
    """
    Analyze tail behavior and extreme events.
    
    Metrics:
    - Outlier frequency: fraction of values beyond μ ± 3σ
    - Extreme wind events: fraction above 95th percentile
    - Calm periods: fraction of near-zero winds (< 0.5 m/s)
    - Max consecutive calm hours
    - Transition intensity: mean |Δy_t| = mean of abs first differences
        Higher → more abrupt changes → harder to predict
    """
    mean, std = series.mean(), series.std()
    n = len(series)
    
    # Outliers
    outlier_mask = (series < mean - 3 * std) | (series > mean + 3 * std)
    
    # Calm periods
    calm_mask = series < 0.5
    if calm_mask.any():
        # Max consecutive calm hours
        calm_groups = (calm_mask != calm_mask.shift()).cumsum()
        calm_runs = calm_mask.groupby(calm_groups).sum()
        max_calm_run = calm_runs.max()
    else:
        max_calm_run = 0
    
    # First differences (transition intensity)
    diffs = series.diff().dropna().abs()
    
    return {
        'outlier_frac': outlier_mask.sum() / n,
        'outlier_count': int(outlier_mask.sum()),
        'extreme_high_frac': (series > series.quantile(0.95)).sum() / n,
        'calm_frac': calm_mask.sum() / n,
        'max_calm_run_hours': int(max_calm_run),
        'transition_mean': diffs.mean(),
        'transition_std': diffs.std(),
        'transition_max': diffs.max(),
        'transition_cv': diffs.std() / diffs.mean() if diffs.mean() > 0 else np.inf,
    }


def predictability_index(desc, acf_info, vol_info, stl_info, freq_info, extreme_info):
    """
    Composite Predictability Index (PI).
    
    Combines multiple factors into a single score [0, 1]:
        Higher PI → more predictable → likely better FL performance (lower MAE)
    
    Components (each normalized to [0, 1], higher = more predictable):
    
    1. Autocorrelation score (weight=0.25):
       = mean ACF(1..24)
       Higher ACF → stronger temporal dependencies → easier to predict
    
    2. Volatility stability score (weight=0.20):
       = 1 - CV(rolling_24h_std)
       Stable volatility → consistent patterns → easier to predict
    
    3. Seasonal strength (weight=0.20):
       = STL seasonal_strength
       Stronger seasonality → more of variance is predictable
    
    4. Spectral concentration (weight=0.15):
       = 1 - spectral_entropy
       Concentrated spectrum → fewer dominant modes → simpler to model
    
    5. Low CV score (weight=0.10):
       = 1 - min(CV, 1)
       Lower coefficient of variation → less relative spread → easier target
    
    6. Low transition score (weight=0.10):
       = 1 - min(transition_CV, 1)
       Smooth changes → gradual evolution → easier to predict
    
    PI = Σ(weight_i × score_i)
    """
    scores = {}
    
    # 1. Autocorrelation
    scores['acf'] = min(max(acf_info['acf_mean_1_24'], 0), 1)
    
    # 2. Volatility stability
    vol_cv = vol_info.get('vol_24h_cv', 1.0)
    scores['vol_stability'] = max(0, 1 - min(vol_cv, 1))
    
    # 3. Seasonal strength
    scores['seasonal'] = stl_info['seasonal_strength'] if stl_info else 0
    
    # 4. Spectral concentration
    scores['spectral'] = max(0, 1 - freq_info['spectral_entropy'])
    
    # 5. Low CV
    scores['low_cv'] = max(0, 1 - min(desc['cv'], 1))
    
    # 6. Low transition intensity
    scores['low_transition'] = max(0, 1 - min(extreme_info['transition_cv'], 1))
    
    weights = {
        'acf': 0.25,
        'vol_stability': 0.20,
        'seasonal': 0.20,
        'spectral': 0.15,
        'low_cv': 0.10,
        'low_transition': 0.10,
    }
    
    pi = sum(weights[k] * scores[k] for k in weights)
    
    return {
        'predictability_index': pi,
        'component_scores': scores,
        'component_weights': weights,
    }


# ============================================================================
# VISUALIZATION FUNCTIONS
# ============================================================================

def plot_distributions(dataset_name, client_data, colors, target_name, output_dir):
    """
    Figure 1: Distribution comparison across clients.
    - Overlaid KDE plots
    - Box plots
    - QQ plots against normal distribution
    """
    n = len(client_data)
    fig = plt.figure(figsize=(20, 12))
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.3)
    
    # 1a. Overlaid KDE
    ax1 = fig.add_subplot(gs[0, 0])
    for name, series in client_data.items():
        series.plot.kde(ax=ax1, label=name, color=colors[name], linewidth=2, alpha=0.8)
    ax1.set_xlabel(f'Wind Speed ({target_name})')
    ax1.set_ylabel('Density')
    ax1.set_title('Kernel Density Estimation (KDE)')
    ax1.legend(fontsize=9)
    ax1.set_xlim(left=0)
    
    # 1b. Box plots
    ax2 = fig.add_subplot(gs[0, 1])
    bp_data = [series.values for series in client_data.values()]
    bp_labels = list(client_data.keys())
    bp = ax2.boxplot(bp_data, labels=bp_labels, patch_artist=True, showmeans=True,
                     meanprops=dict(marker='D', markerfacecolor='black', markersize=5))
    for patch, name in zip(bp['boxes'], client_data.keys()):
        patch.set_facecolor(colors[name])
        patch.set_alpha(0.6)
    ax2.set_ylabel(f'Wind Speed ({target_name})')
    ax2.set_title('Box Plots')
    ax2.tick_params(axis='x', rotation=30)
    
    # 1c. Overlaid histograms
    ax3 = fig.add_subplot(gs[1, 0])
    for name, series in client_data.items():
        ax3.hist(series.values, bins=60, alpha=0.4, label=name, color=colors[name],
                 density=True, edgecolor='none')
    ax3.set_xlabel(f'Wind Speed ({target_name})')
    ax3.set_ylabel('Density')
    ax3.set_title('Histogram (Normalized)')
    ax3.legend(fontsize=9)
    
    # 1d. Descriptive stats table
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis('off')
    stats_rows = []
    for name, series in client_data.items():
        s = compute_descriptive_stats(series)
        stats_rows.append([
            name, f"{s['mean']:.2f}", f"{s['std']:.2f}", f"{s['cv']:.3f}",
            f"{s['skewness']:.2f}", f"{s['kurtosis']:.2f}",
            f"{s['min']:.1f}", f"{s['max']:.1f}"
        ])
    table = ax4.table(
        cellText=stats_rows,
        colLabels=['Client', 'Mean', 'Std', 'CV', 'Skew', 'Kurt', 'Min', 'Max'],
        cellLoc='center', loc='center'
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.5)
    ax4.set_title('Descriptive Statistics', fontsize=13, pad=20)
    
    fig.suptitle(f'{dataset_name} — Distribution Analysis\n'
                 f'CV = σ/μ (higher → harder to predict)  |  '
                 f'Skew > 0 → right tail  |  Kurt > 0 → heavy tails',
                 fontsize=14, fontweight='bold', y=1.02)
    
    path = os.path.join(output_dir, f'{dataset_name.lower()}_01_distributions.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_acf_comparison(dataset_name, client_data, acf_results, colors, output_dir,
                        samples_per_hour=1):
    """
    Figure 2: Autocorrelation comparison.
    - Overlaid ACF curves
    - ACF decay comparison
    - PACF for each client
    """
    n = len(client_data)
    fig = plt.figure(figsize=(20, 10))
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.3)
    
    # 2a. Overlaid ACF
    ax1 = fig.add_subplot(gs[0, 0])
    for name in client_data:
        acf_vals = acf_results[name]['acf_values']
        lags = np.arange(len(acf_vals))
        ax1.plot(lags, acf_vals, label=name, color=colors[name], linewidth=1.5, alpha=0.8)
    ax1.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5, label='0.5 threshold')
    ax1.axhline(y=0, color='black', linewidth=0.5)
    if samples_per_hour == 1:
        x_label = 'Lag (hours)'
    else:
        step_minutes = int(round(60 / samples_per_hour))
        x_label = f'Lag (steps, 1 step = {step_minutes} min)'
    ax1.set_xlabel(x_label)
    ax1.set_ylabel('ACF')
    ax1.set_title('Autocorrelation Function (ACF)\nSlower decay → stronger temporal memory → more predictable')
    ax1.legend(fontsize=8, ncol=2)
    ax1.set_xlim(0, 168 * samples_per_hour)
    
    # 2b. ACF at key lags (bar chart)
    ax2 = fig.add_subplot(gs[0, 1])
    key_lags_hours = [1, 6, 12, 24, 48, 72, 168]
    key_lags_steps = [h * samples_per_hour for h in key_lags_hours]
    x = np.arange(len(key_lags_hours))
    width = 0.8 / n
    for i, name in enumerate(client_data):
        acf_vals = acf_results[name]['acf_values']
        vals = [acf_vals[lag] if lag < len(acf_vals) else 0 for lag in key_lags_steps]
        ax2.bar(x + i * width, vals, width, label=name, color=colors[name], alpha=0.8)
    ax2.set_xlabel(x_label)
    ax2.set_ylabel('ACF')
    ax2.set_xticks(x + width * (n - 1) / 2)
    ax2.set_xticklabels([str(l) for l in key_lags_hours])
    ax2.set_title('ACF at Key Lags\nLag 1=next hour, 24=next day, 168=next week')
    ax2.legend(fontsize=8, ncol=2)
    
    # 2c. ACF summary metrics
    ax3 = fig.add_subplot(gs[1, 0])
    names = list(client_data.keys())
    metrics = ['acf_lag1', 'acf_lag24', 'acf_mean_1_24', 'acf_decay_lag']
    labels = ['ACF(lag=1)', 'ACF(lag=24)', 'Mean ACF(1-24)', 'Decay lag (to 0.5)']
    
    table_data = []
    for name in names:
        row = [name]
        for m in metrics:
            val = acf_results[name][m]
            row.append(f"{val:.3f}" if isinstance(val, float) else str(val))
        table_data.append(row)
    
    ax3.axis('off')
    table = ax3.table(
        cellText=table_data,
        colLabels=['Client'] + labels,
        cellLoc='center', loc='center'
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.5)
    ax3.set_title('ACF Summary Metrics', fontsize=13, pad=20)
    
    # 2d. PACF comparison (first 48 lags)
    ax4 = fig.add_subplot(gs[1, 1])
    max_pacf_lag = 48 * samples_per_hour
    for name in client_data:
        pacf_vals = acf_results[name]['pacf_values']
        lags = np.arange(len(pacf_vals))
        ax4.plot(lags[:max_pacf_lag + 1], pacf_vals[:max_pacf_lag + 1],
                 label=name, color=colors[name], linewidth=1.5, alpha=0.8)
    ax4.axhline(y=0, color='black', linewidth=0.5)
    ax4.set_xlabel(x_label)
    ax4.set_ylabel('PACF')
    ax4.set_title('Partial ACF (first 48 lags)\nShows direct influence of each lag')
    ax4.legend(fontsize=8, ncol=2)
    
    fig.suptitle(f'{dataset_name} — Autocorrelation Analysis\n'
                 f'ACF(k) = Corr(y_t, y_{{t-k}})  |  Higher ACF → more self-predictable',
                 fontsize=14, fontweight='bold', y=1.02)
    
    path = os.path.join(output_dir, f'{dataset_name.lower()}_02_autocorrelation.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_volatility(dataset_name, client_data, vol_results, colors, output_dir):
    """
    Figure 3: Rolling volatility comparison.
    - 24h rolling std time series
    - Distribution of rolling volatility
    - Volatility-of-volatility comparison
    """
    fig = plt.figure(figsize=(20, 12))
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.3)
    
    # 3a. 24h rolling volatility time series (last year only for readability)
    ax1 = fig.add_subplot(gs[0, :])
    for name in client_data:
        vol_series = vol_results[name].get('vol_24h_series')
        if vol_series is not None:
            # Plot last ~8760 hours (1 year)
            plot_series = vol_series.iloc[-8760:] if len(vol_series) > 8760 else vol_series
            ax1.plot(plot_series.index, plot_series.values, label=name,
                     color=colors[name], linewidth=0.8, alpha=0.7)
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Rolling Std (24h window)')
    ax1.set_title('24-Hour Rolling Volatility (last year)\n'
                   'σ_rolling(t) = std(y_{t-23}, ..., y_t)  |  Stable bands → easier to predict')
    ax1.legend(fontsize=9, ncol=3)
    
    # 3b. Distribution of 24h volatility
    ax2 = fig.add_subplot(gs[1, 0])
    for name in client_data:
        vol_series = vol_results[name].get('vol_24h_series')
        if vol_series is not None:
            vol_series.plot.kde(ax=ax2, label=name, color=colors[name], linewidth=2)
    ax2.set_xlabel('Rolling Std (24h)')
    ax2.set_ylabel('Density')
    ax2.set_title('Distribution of Daily Volatility\nWider spread → more regime changes')
    ax2.legend(fontsize=9)
    
    # 3c. Volatility metrics table
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.axis('off')
    table_data = []
    for name in client_data:
        vr = vol_results[name]
        row = [
            name,
            f"{vr.get('vol_24h_mean', 0):.3f}",
            f"{vr.get('vol_24h_cv', 0):.3f}",
            f"{vr.get('vol_168h_mean', 0):.3f}",
            f"{vr.get('vol_168h_cv', 0):.3f}",
            f"{vr.get('vol_720h_mean', 0):.3f}",
            f"{vr.get('vol_720h_cv', 0):.3f}",
        ]
        table_data.append(row)
    
    table = ax3.table(
        cellText=table_data,
        colLabels=['Client', 'σ_24h', 'CV_24h', 'σ_168h', 'CV_168h', 'σ_720h', 'CV_720h'],
        cellLoc='center', loc='center'
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.5)
    ax3.set_title('Volatility Metrics\nCV = std(σ_rolling) / mean(σ_rolling)', fontsize=13, pad=20)
    
    fig.suptitle(f'{dataset_name} — Rolling Volatility Analysis\n'
                 f'CV of volatility: higher → more regime shifts → harder to predict',
                 fontsize=14, fontweight='bold', y=1.02)
    
    path = os.path.join(output_dir, f'{dataset_name.lower()}_03_volatility.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_seasonal_decomposition(dataset_name, client_data, stl_results, colors, output_dir,
                                stl_period, samples_per_hour):
    """
    Figure 4: STL decomposition comparison.
    - Variance decomposition (stacked bars)
    - Seasonal strength comparison
    - Example decomposition for best and worst client
    """
    fig = plt.figure(figsize=(20, 14))
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.3)
    
    names = [n for n in client_data if stl_results[n] is not None]
    
    # 4a. Variance decomposition (stacked bar)
    ax1 = fig.add_subplot(gs[0, 0])
    trend_pcts = [stl_results[n]['trend_pct'] for n in names]
    seas_pcts = [stl_results[n]['seasonal_pct'] for n in names]
    resid_pcts = [stl_results[n]['residual_pct'] for n in names]
    
    x = np.arange(len(names))
    ax1.bar(x, trend_pcts, label='Trend', color='#3498db', alpha=0.8)
    ax1.bar(x, seas_pcts, bottom=trend_pcts, label='Seasonal', color='#2ecc71', alpha=0.8)
    ax1.bar(x, resid_pcts, bottom=[t + s for t, s in zip(trend_pcts, seas_pcts)],
            label='Residual', color='#e74c3c', alpha=0.8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, rotation=30, ha='right')
    ax1.set_ylabel('% of Total Variance')
    period_hours = stl_period / samples_per_hour if samples_per_hour > 0 else stl_period
    ax1.set_title(
        f'Variance Decomposition (STL, period={stl_period} steps ≈ {period_hours:g}h)\n'
        'Less red (residual) → more predictable'
    )
    ax1.legend()
    ax1.set_ylim(0, 105)
    
    # 4b. Seasonal and trend strength
    ax2 = fig.add_subplot(gs[0, 1])
    seasonal_s = [stl_results[n]['seasonal_strength'] for n in names]
    trend_s = [stl_results[n]['trend_strength'] for n in names]
    
    x = np.arange(len(names))
    width = 0.35
    ax2.bar(x - width / 2, seasonal_s, width, label='Seasonal Strength', color='#2ecc71', alpha=0.8)
    ax2.bar(x + width / 2, trend_s, width, label='Trend Strength', color='#3498db', alpha=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=30, ha='right')
    ax2.set_ylabel('Strength [0, 1]')
    ax2.set_title('Seasonal & Trend Strength\n'
                   'Seasonal = 1 - Var(R)/Var(S+R)  |  Closer to 1 → stronger pattern')
    ax2.legend()
    ax2.set_ylim(0, 1.05)
    
    # 4c and 4d: Example decomposition for best and worst seasonal strength
    sorted_by_seasonal = sorted(names, key=lambda n: stl_results[n]['seasonal_strength'], reverse=True)
    best_client = sorted_by_seasonal[0]
    worst_client = sorted_by_seasonal[-1]
    
    for idx, (client, position) in enumerate([(best_client, gs[1, 0]), (worst_client, gs[1, 1])]):
        ax = fig.add_subplot(position)
        stl_res = stl_results[client]['stl_result']
        # Show 2 weeks of data
        n_show = min(int(14 * 24 * samples_per_hour), len(stl_res.seasonal))
        t = np.arange(n_show)
        
        ax.plot(t, stl_res.observed[:n_show], 'k-', alpha=0.4, linewidth=0.8, label='Observed')
        ax.plot(t, stl_res.trend[:n_show], color='#3498db', linewidth=2, label='Trend')
        ax.plot(t, stl_res.seasonal[:n_show], color='#2ecc71', linewidth=1.5, label='Seasonal')
        
        strength = stl_results[client]['seasonal_strength']
        resid_r = stl_results[client]['residual_ratio']
        label = "BEST" if idx == 0 else "WORST"
        ax.set_title(f'{label} Seasonality: {client}\n'
                     f'Seasonal strength={strength:.3f}, Residual ratio={resid_r:.3f}')
        if samples_per_hour == 1:
            x_label = 'Time (hours, 2 weeks shown)'
        else:
            step_minutes = int(round(60 / samples_per_hour))
            x_label = f'Time ({step_minutes}-min steps, 2 weeks shown)'
        ax.set_xlabel(x_label)
        ax.legend(fontsize=8)
    
    fig.suptitle(f'{dataset_name} — Seasonal Decomposition (STL)\n'
                 f'Y_t = Trend_t + Seasonal_t + Residual_t  |  '
                 f'Less residual variance → more predictable',
                 fontsize=14, fontweight='bold', y=1.02)
    
    path = os.path.join(output_dir, f'{dataset_name.lower()}_04_seasonal.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_frequency_spectrum(dataset_name, client_data, freq_results, colors, output_dir):
    """
    Figure 5: Frequency analysis.
    - Power spectrum (log-log)
    - Spectral entropy comparison
    - Power fraction in known cycles
    """
    fig = plt.figure(figsize=(20, 12))
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.3)
    
    # 5a. Power spectrum (period axis, log-log)
    ax1 = fig.add_subplot(gs[0, :])
    for name in client_data:
        periods = freq_results[name]['periods']
        power = freq_results[name]['power']
        # Bin by period for smoother plot
        mask = (periods > 1) & (periods < 10000)
        ax1.loglog(periods[mask], power[mask], label=name, color=colors[name],
                   linewidth=0.8, alpha=0.7)
    
    # Mark known cycles
    for period, label in [(12, '12h'), (24, '24h'), (168, '1 week'), (8760, '1 year')]:
        ax1.axvline(x=period, color='gray', linestyle='--', alpha=0.4, linewidth=1)
        ax1.text(period, ax1.get_ylim()[1] * 0.5, label, fontsize=8, ha='center',
                 va='bottom', color='gray')
    
    ax1.set_xlabel('Period (hours)')
    ax1.set_ylabel('Power')
    ax1.set_title('Power Spectrum (FFT)\nPeaks indicate dominant cycles  |  '
                   'Concentrated peaks → more predictable periodicity')
    ax1.legend(fontsize=9, ncol=3)
    
    # 5b. Spectral entropy comparison
    ax2 = fig.add_subplot(gs[1, 0])
    names = list(client_data.keys())
    entropies = [freq_results[n]['spectral_entropy'] for n in names]
    bars = ax2.bar(names, entropies, color=[colors[n] for n in names], alpha=0.8)
    ax2.set_ylabel('Spectral Entropy (normalized)')
    ax2.set_title('Spectral Entropy\n'
                   'H = -Σ p_i log₂(p_i) / log₂(N)  |  Lower → energy concentrated → predictable')
    ax2.tick_params(axis='x', rotation=30)
    ax2.set_ylim(0, 1.05)
    # Add value labels
    for bar, val in zip(bars, entropies):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                 f'{val:.4f}', ha='center', fontsize=9)
    
    # 5c. Power fraction in known cycles
    ax3 = fig.add_subplot(gs[1, 1])
    cycles = ['diurnal_power_frac', 'semidiurnal_power_frac', 'weekly_power_frac']
    cycle_labels = ['24h (diurnal)', '12h (semi-diurnal)', '168h (weekly)']
    
    x = np.arange(len(names))
    width = 0.8 / len(cycles)
    for i, (cycle, clabel) in enumerate(zip(cycles, cycle_labels)):
        vals = [freq_results[n][cycle] * 100 for n in names]
        ax3.bar(x + i * width, vals, width, label=clabel, alpha=0.8)
    ax3.set_xticks(x + width)
    ax3.set_xticklabels(names, rotation=30, ha='right')
    ax3.set_ylabel('% of Total Spectral Power')
    ax3.set_title('Power in Known Cycles\nHigher → stronger periodic signal')
    ax3.legend(fontsize=9)
    
    fig.suptitle(f'{dataset_name} — Frequency Spectrum Analysis (FFT)\n'
                 f'Windowed FFT with Hann window  |  Peaks = dominant periodicities',
                 fontsize=14, fontweight='bold', y=1.02)
    
    path = os.path.join(output_dir, f'{dataset_name.lower()}_05_frequency.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_extreme_values(dataset_name, client_data, extreme_results, colors, output_dir):
    """
    Figure 6: Extreme value and transition analysis.
    - Transition intensity (|Δy|) distributions
    - Calm fraction and outlier fraction
    - Diurnal pattern (mean by hour-of-day)
    """
    fig = plt.figure(figsize=(20, 12))
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.3)
    
    # 6a. Transition intensity distribution
    ax1 = fig.add_subplot(gs[0, 0])
    for name, series in client_data.items():
        diffs = series.diff().dropna().abs()
        diffs.plot.kde(ax=ax1, label=name, color=colors[name], linewidth=2)
    ax1.set_xlabel('|Δy_t| = |y_t - y_{t-1}| (m/s)')
    ax1.set_ylabel('Density')
    ax1.set_title('Transition Intensity Distribution\n'
                   '|Δy| = absolute hourly change  |  Wider → more abrupt shifts')
    ax1.legend(fontsize=9)
    ax1.set_xlim(0)
    
    # 6b. Extreme metrics bar chart
    ax2 = fig.add_subplot(gs[0, 1])
    names = list(client_data.keys())
    metrics_to_plot = ['calm_frac', 'outlier_frac', 'extreme_high_frac']
    labels = ['Calm (<0.5 m/s)', 'Outliers (>3σ)', 'Extreme high (>P95)']
    
    x = np.arange(len(names))
    width = 0.8 / len(metrics_to_plot)
    for i, (metric, mlabel) in enumerate(zip(metrics_to_plot, labels)):
        vals = [extreme_results[n][metric] * 100 for n in names]
        ax2.bar(x + i * width, vals, width, label=mlabel, alpha=0.8)
    ax2.set_xticks(x + width)
    ax2.set_xticklabels(names, rotation=30, ha='right')
    ax2.set_ylabel('Fraction (%)')
    ax2.set_title('Extreme Event Fractions\nMore calm/outlier periods → harder transitions to predict')
    ax2.legend(fontsize=9)
    
    # 6c. Diurnal pattern (mean by hour of day)
    ax3 = fig.add_subplot(gs[1, 0])
    for name, series in client_data.items():
        hourly_mean = series.groupby(series.index.hour).mean()
        ax3.plot(hourly_mean.index, hourly_mean.values, 'o-', label=name,
                 color=colors[name], linewidth=2, markersize=4)
    ax3.set_xlabel('Hour of Day')
    ax3.set_ylabel('Mean Wind Speed (m/s)')
    ax3.set_title('Diurnal Pattern\n')
    ax3.legend(fontsize=9, ncol=2)
    ax3.set_xticks(range(0, 24, 3))
    ax3.xaxis.set_major_locator(MaxNLocator(integer=True))
    
    # 6d. Monthly pattern
    ax4 = fig.add_subplot(gs[1, 1])
    for name, series in client_data.items():
        monthly_mean = series.groupby(series.index.month).mean()
        ax4.plot(monthly_mean.index, monthly_mean.values, 'o-', label=name,
                 color=colors[name], linewidth=2, markersize=5)
    ax4.set_xlabel('Month')
    ax4.set_ylabel('Mean Wind Speed (m/s)')
    ax4.set_title('Annual Seasonal Pattern\n')
    ax4.legend(fontsize=9, ncol=2)
    ax4.set_xticks(range(1, 13))
    ax4.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], fontsize=9)
    
    fig.suptitle(f'{dataset_name} — Extreme Values & Temporal Patterns\n'
                 f'Transition intensity = |y_t - y_{{t-1}}|  |  '
                 f'Diurnal/annual patterns explain seasonal component',
                 fontsize=14, fontweight='bold', y=1.02)
    
    path = os.path.join(output_dir, f'{dataset_name.lower()}_06_extremes.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_stationarity(dataset_name, client_data, adf_results, colors, output_dir,
                      samples_per_hour=1):
    """
    Figure 7: Stationarity analysis.
    - ADF test statistics
    - Rolling mean and std comparison
    """
    fig = plt.figure(figsize=(20, 10))
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.3)
    
    names = list(client_data.keys())
    
    # 7a. ADF test statistics
    ax1 = fig.add_subplot(gs[0, 0])
    adf_stats = [adf_results[n]['adf_statistic'] for n in names]
    crit_1 = adf_results[names[0]]['adf_critical_1pct']
    crit_5 = adf_results[names[0]]['adf_critical_5pct']
    
    bars = ax1.bar(names, adf_stats, color=[colors[n] for n in names], alpha=0.8)
    ax1.axhline(y=crit_1, color='red', linestyle='--', label=f'1% critical ({crit_1:.2f})')
    ax1.axhline(y=crit_5, color='orange', linestyle='--', label=f'5% critical ({crit_5:.2f})')
    ax1.set_ylabel('ADF Statistic')
    ax1.set_title('Augmented Dickey-Fuller Test\n'
                   'More negative → stronger stationarity evidence')
    ax1.legend(fontsize=9)
    ax1.tick_params(axis='x', rotation=30)
    
    # 7b. ADF p-values
    ax2 = fig.add_subplot(gs[0, 1])
    pvals = [adf_results[n]['adf_pvalue'] for n in names]
    bars = ax2.bar(names, pvals, color=[colors[n] for n in names], alpha=0.8)
    ax2.axhline(y=0.05, color='red', linestyle='--', label='p=0.05 threshold')
    ax2.set_ylabel('p-value')
    ax2.set_title('ADF p-values\n'
                   'H₀: non-stationary  |  p < 0.05 → reject → stationary')
    ax2.legend(fontsize=9)
    ax2.tick_params(axis='x', rotation=30)
    for bar, val in zip(bars, pvals):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.001,
                 f'{val:.4f}', ha='center', fontsize=9)
    
    # 7c & 7d. Rolling mean comparison (720h window)
    ax3 = fig.add_subplot(gs[1, :])
    window = 720 * samples_per_hour
    min_periods = 360 * samples_per_hour
    for name, series in client_data.items():
        rolling_mean = series.rolling(window=window, min_periods=min_periods).mean().dropna()
        # Plot last 2 years
        plot_series = rolling_mean.iloc[-17520:] if len(rolling_mean) > 17520 else rolling_mean
        ax3.plot(plot_series.index, plot_series.values, label=name,
                 color=colors[name], linewidth=1.5, alpha=0.8)
    ax3.set_xlabel('Date')
    ax3.set_ylabel('Rolling Mean (720h / 30-day window)')
    ax3.set_title('Long-term Trend Comparison\n'
                   'Stable mean → stationary → consistent training data distribution')
    ax3.legend(fontsize=9, ncol=3)
    
    fig.suptitle(f'{dataset_name} — Stationarity Analysis (ADF Test)\n'
                 f'ADF tests H₀: unit root exists (non-stationary)  |  '
                 f'All should reject → wind speed is stationary',
                 fontsize=14, fontweight='bold', y=1.02)
    
    path = os.path.join(output_dir, f'{dataset_name.lower()}_07_stationarity.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_predictability_dashboard(dataset_name, client_data, all_results, colors, output_dir):
    """
    Figure 8: Composite predictability dashboard.
    - Predictability Index (PI) ranking
    - Spider/radar chart of component scores
    - PI vs known FL MAE ranking correlation
    """
    names = list(client_data.keys())
    pi_results = all_results['predictability']
    
    fig = plt.figure(figsize=(20, 10))
    gs = gridspec.GridSpec(1, 2, wspace=0.3)
    
    # 8a. PI bar chart (ranked)
    ax1 = fig.add_subplot(gs[0, 0])
    pi_scores = {n: pi_results[n]['predictability_index'] for n in names}
    sorted_names = sorted(pi_scores, key=pi_scores.get, reverse=True)
    sorted_scores = [pi_scores[n] for n in sorted_names]
    sorted_colors = [colors[n] for n in sorted_names]
    
    bars = ax1.barh(range(len(sorted_names)), sorted_scores, color=sorted_colors, alpha=0.8)
    ax1.set_yticks(range(len(sorted_names)))
    ax1.set_yticklabels(sorted_names)
    ax1.set_xlabel('Predictability Index [0, 1]')
    ax1.set_title('Composite Predictability Index (PI)\n'
                   'Higher → data is more inherently predictable → expect lower MAE')
    ax1.invert_yaxis()
    
    for bar, val in zip(bars, sorted_scores):
        ax1.text(bar.get_width() + 0.005, bar.get_y() + bar.get_height() / 2,
                 f'{val:.4f}', va='center', fontsize=10)
    
    # 8b. Component breakdown (grouped horizontal bars)
    ax2 = fig.add_subplot(gs[0, 1])
    components = list(pi_results[names[0]]['component_scores'].keys())
    comp_labels = {
        'acf': 'ACF (0.25)',
        'vol_stability': 'Vol Stability (0.20)',
        'seasonal': 'Seasonality (0.20)',
        'spectral': 'Spectral Conc. (0.15)',
        'low_cv': 'Low CV (0.10)',
        'low_transition': 'Low Transition (0.10)',
    }
    
    y = np.arange(len(sorted_names))
    total_width = 0.8
    width = total_width / len(components)
    
    for i, comp in enumerate(components):
        vals = [pi_results[n]['component_scores'][comp] for n in sorted_names]
        ax2.barh(y + i * width, vals, width, label=comp_labels.get(comp, comp), alpha=0.8)
    
    ax2.set_yticks(y + total_width / 2)
    ax2.set_yticklabels(sorted_names)
    ax2.set_xlabel('Component Score [0, 1]')
    ax2.set_title('PI Component Breakdown\n'
                   'PI = Σ(weight_i × score_i)  |  See legend for weights')
    ax2.legend(fontsize=8, loc='lower right')
    ax2.invert_yaxis()
    ax2.set_xlim(0, 1.05)
    
    fig.suptitle(f'{dataset_name} — Predictability Index Dashboard\n'
                 f'PI = 0.25·ACF + 0.20·VolStab + 0.20·Seasonal + '
                 f'0.15·Spectral + 0.10·LowCV + 0.10·LowTransition',
                 fontsize=14, fontweight='bold', y=1.02)
    
    path = os.path.join(output_dir, f'{dataset_name.lower()}_08_predictability.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_cross_client_summary(dataset_name, client_data, all_results, colors, output_dir):
    """
    Figure 9: Master summary table + correlation heatmap.
    """
    names = list(client_data.keys())
    
    fig = plt.figure(figsize=(22, 10))
    gs = gridspec.GridSpec(1, 2, wspace=0.25, width_ratios=[1.5, 1])
    
    # 9a. Master summary table
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.axis('off')
    
    headers = ['Client', 'Mean', 'CV', 'ACF(1)', 'ACF(24)',
               'Decay\nLag', 'Seas.\nStr.', 'Resid\n%', 'Spec.\nEntropy',
               'Trans.\nMean', 'PI']
    
    table_data = []
    for n in names:
        desc = all_results['descriptive'][n]
        acf_r = all_results['acf'][n]
        stl_r = all_results['seasonal'][n]
        freq_r = all_results['frequency'][n]
        ext_r = all_results['extreme'][n]
        pi_r = all_results['predictability'][n]
        
        row = [
            n,
            f"{desc['mean']:.2f}",
            f"{desc['cv']:.3f}",
            f"{acf_r['acf_lag1']:.3f}",
            f"{acf_r['acf_lag24']:.3f}",
            f"{acf_r['acf_decay_lag']}",
            f"{stl_r['seasonal_strength']:.3f}" if stl_r else "N/A",
            f"{stl_r['residual_pct']:.1f}" if stl_r else "N/A",
            f"{freq_r['spectral_entropy']:.4f}",
            f"{ext_r['transition_mean']:.3f}",
            f"{pi_r['predictability_index']:.4f}",
        ]
        table_data.append(row)
    
    table = ax1.table(
        cellText=table_data,
        colLabels=headers,
        cellLoc='center', loc='center'
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.8)

    # Color cells by PI (last column, index 10)
    pi_vals = [all_results['predictability'][n]['predictability_index'] for n in names]
    pi_min, pi_max = min(pi_vals), max(pi_vals)
    for i, n in enumerate(names):
        pi = all_results['predictability'][n]['predictability_index']
        norm = (pi - pi_min) / (pi_max - pi_min) if pi_max > pi_min else 0.5
        # Green for high PI, red for low
        r = 1 - norm * 0.6
        g = 0.4 + norm * 0.6
        b = 0.4
        table[i + 1, 10].set_facecolor((r, g, b, 0.3))
    
    ax1.set_title('Master Summary Table', fontsize=14, pad=30)
    
    # 9b. Correlation matrix of key metrics
    ax2 = fig.add_subplot(gs[0, 1])
    
    metric_names = ['Mean', 'CV', 'ACF(1)', 'ACF(24)', 'Seas.Str.', 'Resid%', 'Spec.Ent.', 'Trans.Mean', 'PI']
    metric_matrix = []
    for n in names:
        desc = all_results['descriptive'][n]
        acf_r = all_results['acf'][n]
        stl_r = all_results['seasonal'][n]
        freq_r = all_results['frequency'][n]
        ext_r = all_results['extreme'][n]
        pi_r = all_results['predictability'][n]
        
        metric_matrix.append([
            desc['mean'], desc['cv'], acf_r['acf_lag1'], acf_r['acf_lag24'],
            stl_r['seasonal_strength'] if stl_r else 0,
            stl_r['residual_pct'] if stl_r else 100,
            freq_r['spectral_entropy'], ext_r['transition_mean'],
            pi_r['predictability_index'],
        ])
    
    df_metrics = pd.DataFrame(metric_matrix, columns=metric_names, index=names)
    corr = df_metrics.T.corr() if len(names) > 2 else df_metrics.corr()
    
    # If we have enough clients, show metric-to-metric correlation
    if len(names) >= 3:
        # Rank clients by each metric and show rank matrix
        rank_df = df_metrics.rank(ascending=False)
        im = ax2.imshow(rank_df.values, cmap='RdYlGn_r', aspect='auto')
        ax2.set_xticks(range(len(metric_names)))
        ax2.set_xticklabels(metric_names, rotation=45, ha='right', fontsize=9)
        ax2.set_yticks(range(len(names)))
        ax2.set_yticklabels(names, fontsize=10)
        
        # Annotate with ranks
        for i in range(len(names)):
            for j in range(len(metric_names)):
                ax2.text(j, i, f'{int(rank_df.values[i, j])}',
                         ha='center', va='center', fontsize=9, fontweight='bold')
        
        plt.colorbar(im, ax=ax2, label='Rank (1=best)')
        ax2.set_title('Client Ranking Across Metrics\n'
                       '1 = best for predictability', fontsize=12)
    else:
        ax2.text(0.5, 0.5, 'Need ≥3 clients\nfor ranking matrix',
                 ha='center', va='center', fontsize=14, transform=ax2.transAxes)
    
    fig.suptitle(f'{dataset_name} — Cross-Client Comparison Dashboard',
                 fontsize=14, fontweight='bold', y=1.02)
    
    path = os.path.join(output_dir, f'{dataset_name.lower()}_09_summary.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def analyze_dataset(dataset_name, client_data, colors, target_name, output_dir,
                    stl_period, samples_per_hour):
    """Run full analysis pipeline for one dataset."""
    
    print(f"\n{'='*70}")
    print(f"  ANALYZING: {dataset_name} ({len(client_data)} clients)")
    print(f"{'='*70}")
    
    all_results = {
        'descriptive': {},
        'adf': {},
        'acf': {},
        'volatility': {},
        'seasonal': {},
        'frequency': {},
        'extreme': {},
        'predictability': {},
    }
    
    for name, series in client_data.items():
        print(f"\n  --- {name} ---")
        
        print(f"    Descriptive stats...")
        all_results['descriptive'][name] = compute_descriptive_stats(series)
        
        print(f"    ADF test...")
        all_results['adf'][name] = adf_test(series)
        
        print(f"    Autocorrelation...")
        all_results['acf'][name] = autocorrelation_analysis(series, samples_per_hour=samples_per_hour)
        
        print(f"    Rolling volatility...")
        all_results['volatility'][name] = rolling_volatility(series, samples_per_hour=samples_per_hour)
        
        print(f"    Seasonal decomposition (STL)...")
        all_results['seasonal'][name] = seasonal_decomposition(series, period=stl_period)
        
        print(f"    Frequency analysis (FFT)...")
        all_results['frequency'][name] = frequency_analysis(series, samples_per_hour=samples_per_hour)
        
        print(f"    Extreme value analysis...")
        all_results['extreme'][name] = extreme_value_analysis(series)
        
        print(f"    Computing predictability index...")
        all_results['predictability'][name] = predictability_index(
            all_results['descriptive'][name],
            all_results['acf'][name],
            all_results['volatility'][name],
            all_results['seasonal'][name],
            all_results['frequency'][name],
            all_results['extreme'][name],
        )
        pi = all_results['predictability'][name]['predictability_index']
        print(f"    → PI = {pi:.4f}")
    
    # Generate all visualizations
    print(f"\n  Generating visualizations...")
    
    plot_distributions(dataset_name, client_data, colors, target_name, output_dir)
    plot_acf_comparison(dataset_name, client_data, all_results['acf'], colors, output_dir,
                        samples_per_hour=samples_per_hour)
    plot_volatility(dataset_name, client_data, all_results['volatility'], colors, output_dir)
    plot_seasonal_decomposition(
        dataset_name, client_data, all_results['seasonal'], colors, output_dir,
        stl_period, samples_per_hour
    )
    plot_frequency_spectrum(dataset_name, client_data, all_results['frequency'], colors, output_dir)
    plot_extreme_values(dataset_name, client_data, all_results['extreme'], colors, output_dir)
    plot_stationarity(dataset_name, client_data, all_results['adf'], colors, output_dir,
                      samples_per_hour=samples_per_hour)
    plot_predictability_dashboard(dataset_name, client_data, all_results, colors, output_dir)
    plot_cross_client_summary(dataset_name, client_data, all_results, colors, output_dir)
    
    # Print final summary
    print(f"\n  {'='*50}")
    print(f"  PREDICTABILITY INDEX RANKING — {dataset_name}")
    print(f"  {'='*50}")
    pi_sorted = sorted(
        all_results['predictability'].items(),
        key=lambda x: x[1]['predictability_index'],
        reverse=True
    )
    for rank, (name, pi_data) in enumerate(pi_sorted, 1):
        pi = pi_data['predictability_index']
        comps = pi_data['component_scores']
        print(f"  {rank}. {name:15s}  PI={pi:.4f}  "
              f"[ACF={comps['acf']:.3f}, Vol={comps['vol_stability']:.3f}, "
              f"Seas={comps['seasonal']:.3f}, Spec={comps['spectral']:.3f}]")
    
    return all_results


def save_all_results_to_csv(results, output_dir):
    """
    Export all findings to two CSV files:
    1. detailed_metrics.csv — all descriptive, statistical, and component metrics
    2. composite_findings.csv — predictability index and summary scores
    """
    detailed_rows = []
    composite_rows = []

    for dataset_name, ds_results in results.items():
        # Iterate through each client
        for client_name in ds_results['descriptive'].keys():
            detailed_row = {'dataset': dataset_name, 'client': client_name}
            composite_row = {'dataset': dataset_name, 'client': client_name}

            # 1. DESCRIPTIVE STATISTICS
            desc = ds_results['descriptive'][client_name]
            for key, val in desc.items():
                detailed_row[f'desc_{key}'] = val

            # 2. ADF TEST RESULTS
            adf = ds_results['adf'][client_name]
            for key in ['adf_statistic', 'adf_pvalue', 'adf_lags_used', 'adf_nobs',
                        'adf_critical_1pct', 'adf_critical_5pct', 'adf_stationary']:
                detailed_row[f'adf_{key}'] = adf.get(key, None)

            # 3. AUTOCORRELATION RESULTS
            acf_res = ds_results['acf'][client_name]
            for key in ['acf_lag1', 'acf_lag24', 'acf_mean_1_24', 'acf_mean_1_168',
                        'acf_decay_lag', 'ljungbox_pvalue']:
                detailed_row[f'acf_{key}'] = acf_res.get(key, None)

            # 4. VOLATILITY RESULTS
            vol = ds_results['volatility'][client_name]
            for key in ['vol_24h_mean', 'vol_24h_std', 'vol_24h_cv',
                        'vol_168h_mean', 'vol_168h_std', 'vol_168h_cv',
                        'vol_720h_mean', 'vol_720h_std', 'vol_720h_cv']:
                detailed_row[f'vol_{key}'] = vol.get(key, None)

            # 5. SEASONAL DECOMPOSITION RESULTS
            if ds_results['seasonal'][client_name] is not None:
                seas = ds_results['seasonal'][client_name]
                for key in ['var_total', 'var_trend', 'var_seasonal', 'var_resid',
                            'residual_ratio', 'seasonal_strength', 'trend_strength',
                            'trend_pct', 'seasonal_pct', 'residual_pct']:
                    detailed_row[f'seas_{key}'] = seas.get(key, None)
            else:
                for key in ['var_total', 'var_trend', 'var_seasonal', 'var_resid',
                            'residual_ratio', 'seasonal_strength', 'trend_strength',
                            'trend_pct', 'seasonal_pct', 'residual_pct']:
                    detailed_row[f'seas_{key}'] = None

            # 6. FREQUENCY ANALYSIS RESULTS
            freq = ds_results['frequency'][client_name]
            for key in ['spectral_entropy', 'dominant_period', 'dominant_power',
                        'diurnal_power_frac', 'semidiurnal_power_frac', 'weekly_power_frac']:
                detailed_row[f'freq_{key}'] = freq.get(key, None)

            # 7. EXTREME VALUE ANALYSIS RESULTS
            extr = ds_results['extreme'][client_name]
            for key in ['calm_frac', 'outlier_frac', 'extreme_high_frac',
                        'mean_transition', 'median_transition', 'p95_transition']:
                detailed_row[f'extr_{key}'] = extr.get(key, None)

            # 8. PREDICTABILITY INDEX & COMPONENTS
            pred = ds_results['predictability'][client_name]
            composite_row['predictability_index'] = pred.get('predictability_index', None)
            for comp_name, comp_score in pred.get('component_scores', {}).items():
                composite_row[f'component_{comp_name}'] = comp_score

            detailed_rows.append(detailed_row)
            composite_rows.append(composite_row)

    # Save to CSV files
    if detailed_rows:
        df_detailed = pd.DataFrame(detailed_rows)
        detailed_path = os.path.join(output_dir, 'detailed_metrics.csv')
        df_detailed.to_csv(detailed_path, index=False)
        print(f"\n✓ Saved detailed metrics: {detailed_path}")
        print(f"  Columns: {len(df_detailed.columns)}, Rows: {len(df_detailed)}")

    if composite_rows:
        df_composite = pd.DataFrame(composite_rows)
        composite_path = os.path.join(output_dir, 'composite_findings.csv')
        df_composite.to_csv(composite_path, index=False)
        print(f"✓ Saved composite findings: {composite_path}")
        print(f"  Columns: {len(df_composite.columns)}, Rows: {len(df_composite)}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}\n")

    # ---- Load NASA POWER (Kazakhstan) ----
    print("Loading NASA POWER datasets (Kazakhstan cities)...")
    nasa_data = {}
    for city, filename in NASA_FILES.items():
        try:
            nasa_data[city] = load_nasa(city, filename)
        except Exception as e:
            print(f"  ERROR loading {city}: {e}")

    # ---- Load VNMET (Vietnam) ----
    print("\nLoading VNMET datasets (Vietnam stations)...")
    vnmet_data = {}
    for station, filename in VNMET_FILES.items():
        try:
            vnmet_data[station] = load_vnmet(station, filename)
        except Exception as e:
            print(f"  ERROR loading {station}: {e}")

    # ---- Run analysis ----
    results = {}

    if nasa_data:
        results['NASA'] = analyze_dataset(
            'NASA_POWER', nasa_data, NASA_COLORS, NASA_TARGET, OUTPUT_DIR,
            NASA_STL_PERIOD, NASA_SAMPLES_PER_HOUR
        )

    if vnmet_data:
        results['VNMET'] = analyze_dataset(
            'VNMET', vnmet_data, VNMET_COLORS, VNMET_TARGET, OUTPUT_DIR,
            VNMET_STL_PERIOD, VNMET_SAMPLES_PER_HOUR
        )

    # ---- Export all results to CSV ----
    print(f"\n{'='*70}")
    print(f"  EXPORTING RESULTS TO CSV")
    print(f"{'='*70}")
    save_all_results_to_csv(results, OUTPUT_DIR)

    # ---- Print final cross-dataset comparison ----
    print(f"\n{'='*70}")
    print(f"  CROSS-DATASET COMPARISON")
    print(f"{'='*70}")

    for ds_name, ds_results in results.items():
        pi_data = ds_results['predictability']
        pi_vals = [v['predictability_index'] for v in pi_data.values()]
        print(f"\n  {ds_name}:")
        print(f"    PI range: [{min(pi_vals):.4f}, {max(pi_vals):.4f}]")
        print(f"    PI spread: {max(pi_vals) - min(pi_vals):.4f}")

        # Best and worst
        best = max(pi_data, key=lambda k: pi_data[k]['predictability_index'])
        worst = min(pi_data, key=lambda k: pi_data[k]['predictability_index'])
        print(f"    Most predictable:  {best} (PI={pi_data[best]['predictability_index']:.4f})")
        print(f"    Least predictable: {worst} (PI={pi_data[worst]['predictability_index']:.4f})")

    print(f"\n{'='*70}")
    print(f"  All figures saved to: {OUTPUT_DIR}")
    print(f"  Total figures: {len(nasa_data) > 0 and 9 or 0} (NASA) + {len(vnmet_data) > 0 and 9 or 0} (VNMET) = {(len(nasa_data) > 0) * 9 + (len(vnmet_data) > 0) * 9}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
