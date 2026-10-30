#!/usr/bin/env python3
"""
Comprehensive Experiment Analysis Script

Aggregates all federated learning experiments into a single CSV file with:
- Model and FL parameters
- Performance metrics (loss, MAE, RMSE)
- Time performance (training duration, time per round)
- Best round information

Usage:
    python analyze_experiments.py
    python analyze_experiments.py --output results_summary.csv
    python analyze_experiments.py --exp-dir /path/to/experiments
"""

import argparse
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import numpy as np


def parse_config_file(config_path: str) -> Dict[str, any]:
    """Parse experiment configuration file"""
    config = {}

    if not os.path.exists(config_path):
        return config

    with open(config_path, 'r') as f:
        content = f.read()

    # Parse sections
    sections = {
        'Federated Learning Parameters': 'fl_',
        'Model Architecture Parameters': 'model_',
        'Data Parameters': 'data_'
    }

    current_section = None
    for line in content.split('\n'):
        line = line.strip()

        # Check if this is a section header
        for section_name, prefix in sections.items():
            if section_name in line:
                current_section = prefix
                break

        # Parse parameter lines (format: "  key: value")
        if ':' in line and current_section:
            # Remove leading spaces and split by ':'
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()

                # Try to convert to appropriate type
                try:
                    # Try int first
                    value = int(value)
                except ValueError:
                    try:
                        # Try float
                        value = float(value)
                    except ValueError:
                        # Keep as string
                        pass

                config[current_section + key] = value

    return config


def parse_timestamp_from_folder(folder_name: str) -> Optional[str]:
    """Extract timestamp from experiment folder name"""
    match = re.search(r'(\d{8}_\d{6})', folder_name)
    if match:
        return match.group(1)
    return None


def get_experiment_name(folder_name: str) -> str:
    """Extract experiment name from folder"""
    # Remove "experiments_" prefix and timestamp
    name = folder_name.replace('experiments_', '')
    # Remove timestamp pattern
    name = re.sub(r'_\d{8}_\d{6}$', '', name)
    return name if name else 'default'


def analyze_single_experiment(exp_folder: str) -> Optional[Dict]:
    """Analyze a single experiment folder and extract all relevant information"""

    exp_path = Path(exp_folder)
    if not exp_path.exists():
        return None

    result = {
        'experiment_folder': exp_path.name,
        'experiment_name': get_experiment_name(exp_path.name),
        'timestamp': parse_timestamp_from_folder(exp_path.name),
    }

    # Parse configuration
    config_path = exp_path / "config.txt"
    if config_path.exists():
        config = parse_config_file(str(config_path))
        result.update(config)

    # Parse training summary
    training_summary_path = exp_path / "training_summary.csv"
    if training_summary_path.exists():
        try:
            df_train = pd.read_csv(training_summary_path)

            # Get final round metrics
            if len(df_train) > 0:
                final_round = df_train.iloc[-1]
                result['final_round'] = int(final_round['round'])
                result['final_train_loss'] = float(final_round['train_loss']) if pd.notna(final_round.get('train_loss')) else None
                result['final_val_loss'] = float(final_round['val_loss']) if pd.notna(final_round.get('val_loss')) else None
                result['final_val_mae'] = float(final_round['val_mae']) if pd.notna(final_round.get('val_mae')) else None
                result['final_val_rmse'] = float(final_round['val_rmse']) if pd.notna(final_round.get('val_rmse')) else None

                # Get best validation loss and corresponding round
                best_idx = df_train['val_loss'].idxmin()
                best_round = df_train.iloc[best_idx]
                result['best_round'] = int(best_round['round'])
                result['best_val_loss'] = float(best_round['val_loss'])
                result['best_val_mae'] = float(best_round['val_mae']) if pd.notna(best_round.get('val_mae')) else None
                result['best_val_rmse'] = float(best_round['val_rmse']) if pd.notna(best_round.get('val_rmse')) else None

                # Calculate average metrics across all rounds
                result['avg_train_loss'] = float(df_train['train_loss'].mean()) if 'train_loss' in df_train.columns else None
                result['avg_val_loss'] = float(df_train['val_loss'].mean())
                result['avg_val_mae'] = float(df_train['val_mae'].mean()) if 'val_mae' in df_train.columns else None
                result['avg_val_rmse'] = float(df_train['val_rmse'].mean()) if 'val_rmse' in df_train.columns else None

                # Time metrics from training summary
                if 'round_duration_sec' in df_train.columns:
                    result['avg_round_duration_sec'] = float(df_train['round_duration_sec'].mean())
                    result['total_round_duration_sec'] = float(df_train['round_duration_sec'].sum())

                if 'validation_duration_sec' in df_train.columns:
                    result['avg_validation_duration_sec'] = float(df_train['validation_duration_sec'].mean())
                    result['total_validation_duration_sec'] = float(df_train['validation_duration_sec'].sum())

                if 'avg_client_train_duration_sec' in df_train.columns:
                    result['avg_client_train_duration_sec'] = float(df_train['avg_client_train_duration_sec'].mean())

                if 'max_client_train_duration_sec' in df_train.columns:
                    result['max_client_train_duration_sec'] = float(df_train['max_client_train_duration_sec'].max())

                if 'avg_client_drift' in df_train.columns:
                    result['avg_client_drift'] = float(df_train['avg_client_drift'].mean())

                if 'max_client_drift' in df_train.columns:
                    result['max_client_drift'] = float(df_train['max_client_drift'].max())

                # --- Communication Efficiency ---
                num_clients = result.get('num_clients', result.get('fl_num-clients', 5))
                fraction_train = result.get('fl_fraction-train', 1.0)
                clients_per_round = max(1, int(num_clients * fraction_train))

                if 'payload_sent_mb' in df_train.columns and 'payload_received_mb' in df_train.columns:
                    # comm = (sum_sent + sum_recv) * clients_per_round
                    round_comm_mb = (df_train['payload_sent_mb'] + df_train['payload_received_mb']) * clients_per_round
                    result['total_comm_mb'] = float(round_comm_mb.sum())
                    
                    # rounds_to_target (MAE < 0.5 default)
                    target_mae = 0.5
                    reached_target = df_train[df_train['val_mae'] < target_mae]
                    if not reached_target.empty:
                        first_round = int(reached_target.iloc[0]['round'])
                        result['rounds_to_target'] = first_round
                        # comm_to_target = cumulative comm up to that round
                        result['comm_to_target'] = float(round_comm_mb.iloc[:first_round].sum())
                    else:
                        result['rounds_to_target'] = None
                        result['comm_to_target'] = None
                elif 'payload_sent_mb' in df_train.columns:
                    # Fallback to user formula if received is missing
                    total_sent = df_train['payload_sent_mb'].sum()
                    result['total_comm_mb'] = float(total_sent * clients_per_round * 2)

                # --- Fairness Metrics Calculation ---
                best_round_num = result.get('best_round')
                metrics_dir = exp_path / "metrics"
                if best_round_num is not None and metrics_dir.exists():
                    client_maes = []
                    for client_file in metrics_dir.glob("client*_eval_metrics.csv"):
                        try:
                            df_client = pd.read_csv(client_file)
                            # Get the MAE for the best round
                            best_client_row = df_client[df_client['round'] == best_round_num]
                            if not best_client_row.empty:
                                # Use test_mae if available, else val_mae
                                mae = best_client_row.iloc[0].get('test_mae', best_client_row.iloc[0].get('val_mae'))
                                if pd.notna(mae):
                                    client_maes.append(float(mae))
                        except Exception as ce:
                            print(f"Warning: Error parsing client metrics {client_file}: {ce}")

                    if client_maes:
                        result['client_mae_std'] = float(np.std(client_maes))
                        result['worst_client_mae'] = float(np.max(client_maes))
                        result['best_client_mae'] = float(np.min(client_maes))
                        if result['best_client_mae'] > 0:
                            result['fairness_ratio'] = result['worst_client_mae'] / result['best_client_mae']
                        else:
                            result['fairness_ratio'] = None

        except Exception as e:
            print(f"Warning: Error parsing training summary for {exp_folder}: {e}")

    # Parse timing summary
    timing_summary_path = exp_path / "timing_summary.csv"
    if timing_summary_path.exists():
        try:
            df_timing = pd.read_csv(timing_summary_path)
            if len(df_timing) > 0:
                timing = df_timing.iloc[0]
                result['total_training_time_sec'] = float(timing['total_training_time_sec'])
                result['total_training_time_min'] = float(timing['total_training_time_min'])
                result['start_timestamp'] = str(timing['start_timestamp'])
                result['end_timestamp'] = str(timing['end_timestamp'])
        except Exception as e:
            print(f"Warning: Error parsing timing summary for {exp_folder}: {e}")

    return result


def find_experiment_folders(base_path: str = ".") -> List[str]:
    """Find all experiment folders in the base path"""
    exp_folders = []

    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        if os.path.isdir(item_path) and item.startswith("experiments_"):
            exp_folders.append(item_path)

    # Sort by timestamp (newest first)
    exp_folders.sort(reverse=True)

    return exp_folders


def create_summary_table(experiments: List[Dict]) -> pd.DataFrame:
    """Create a comprehensive summary table from experiment data"""

    if not experiments:
        return pd.DataFrame()

    df = pd.DataFrame(experiments)

    # Define column order for better readability
    # Start with identification columns
    id_cols = ['experiment_name', 'timestamp', 'experiment_folder']

    # FL parameters
    fl_cols = [col for col in df.columns if col.startswith('fl_')]

    # Model parameters
    model_cols = [col for col in df.columns if col.startswith('model_')]

    # Best metrics
    best_cols = ['best_round', 'best_val_loss', 'best_val_mae', 'best_val_rmse']

    # Fairness metrics
    fairness_cols = ['client_mae_std', 'worst_client_mae', 'best_client_mae', 'fairness_ratio']

    # Final metrics
    final_cols = ['final_round', 'final_val_loss', 'final_val_mae', 'final_val_rmse',
                  'final_train_loss']

    # Average metrics
    avg_cols = ['avg_val_loss', 'avg_val_mae', 'avg_val_rmse', 'avg_train_loss']

    # Time metrics
    time_cols = ['total_training_time_sec', 'total_training_time_min',
                 'avg_round_duration_sec', 'avg_validation_duration_sec',
                 'avg_client_train_duration_sec', 'max_client_train_duration_sec',
                 'avg_client_drift', 'max_client_drift']

    # Communication and Convergence metrics
    comm_cols = ['total_comm_mb', 'rounds_to_target', 'comm_to_target']

    # Other columns
    other_cols = [col for col in df.columns if col not in
                  id_cols + fl_cols + model_cols + best_cols + fairness_cols + final_cols + avg_cols + time_cols + comm_cols]

    # Combine in desired order
    ordered_cols = []
    for col_group in [id_cols, fl_cols, model_cols, best_cols, fairness_cols, final_cols, avg_cols, time_cols, comm_cols, other_cols]:
        for col in col_group:
            if col in df.columns:
                ordered_cols.append(col)

    df = df[ordered_cols]

    return df


def print_summary_stats(df: pd.DataFrame):
    """Print summary statistics"""
    print("\n" + "="*80)
    print("EXPERIMENT SUMMARY STATISTICS")
    print("="*80)

    print(f"\nTotal experiments: {len(df)}")

    if len(df) == 0:
        return

    # Group by experiment name
    if 'experiment_name' in df.columns:
        print(f"\nExperiments by type:")
        for name, group in df.groupby('experiment_name'):
            print(f"  {name}: {len(group)} runs")

    # Best performing experiments
    if 'best_val_loss' in df.columns:
        print(f"\n{'='*80}")
        print("TOP 5 EXPERIMENTS BY VALIDATION LOSS")
        print("="*80)
        top_5 = df.nsmallest(5, 'best_val_loss')
        display_cols = ['experiment_name', 'best_round', 'best_val_loss', 'best_val_mae',
                       'total_comm_mb', 'rounds_to_target', 'total_training_time_min']
        display_cols = [c for c in display_cols if c in df.columns]

        print(top_5[display_cols].to_string(index=False))

    # Time performance
    if 'total_training_time_min' in df.columns:
        print(f"\n{'='*80}")
        print("TIME PERFORMANCE")
        print("="*80)
        print(f"Average training time: {df['total_training_time_min'].mean():.2f} minutes")
        print(f"Fastest experiment: {df['total_training_time_min'].min():.2f} minutes")
        print(f"Slowest experiment: {df['total_training_time_min'].max():.2f} minutes")

    # Prediction length comparison (if available)
    if 'model_pred_len' in df.columns:
        print(f"\n{'='*80}")
        print("PERFORMANCE BY PREDICTION LENGTH")
        print("="*80)
        pred_len_groups = df.groupby('model_pred_len').agg({
            'best_val_loss': ['mean', 'std', 'min'],
            'best_val_mae': ['mean', 'std', 'min'],
            'total_training_time_min': ['mean', 'std']
        })
        print(pred_len_groups)

    # Client number comparison (if available)
    if 'fl_num-clients' in df.columns:
        print(f"\n{'='*80}")
        print("PERFORMANCE BY NUMBER OF CLIENTS")
        print("="*80)
        client_groups = df.groupby('fl_num-clients').agg({
            'best_val_loss': ['mean', 'std', 'min'],
            'total_training_time_min': ['mean', 'std']
        })
        print(client_groups)

    print("\n" + "="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze federated learning experiments and create comprehensive summary",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument('--exp-dir', type=str, default='.',
                       help='Directory containing experiment folders')
    parser.add_argument('--output', type=str, default='all_experiments_summary.csv',
                       help='Output CSV file path')
    parser.add_argument('--quiet', action='store_true',
                       help='Suppress console output')
    parser.add_argument('--stats-only', action='store_true',
                       help='Only print statistics, do not save CSV')

    args = parser.parse_args()

    if not args.quiet:
        print("\n" + "="*80)
        print("FEDERATED LEARNING EXPERIMENT ANALYSIS")
        print("="*80)
        print(f"\nScanning for experiments in: {os.path.abspath(args.exp_dir)}")

    # Find all experiment folders
    exp_folders = find_experiment_folders(args.exp_dir)

    if not args.quiet:
        print(f"Found {len(exp_folders)} experiment folders\n")

    if len(exp_folders) == 0:
        print("No experiment folders found!")
        print("Experiment folders should start with 'experiments_'")
        return

    # Analyze each experiment
    experiments = []
    for folder in exp_folders:
        if not args.quiet:
            print(f"Analyzing: {os.path.basename(folder)}...")

        exp_data = analyze_single_experiment(folder)
        if exp_data:
            experiments.append(exp_data)

    if len(experiments) == 0:
        print("\nNo valid experiment data found!")
        return

    # Create summary dataframe
    df_summary = create_summary_table(experiments)

    # Print statistics
    if not args.quiet:
        print_summary_stats(df_summary)

    # Save to CSV
    if not args.stats_only:
        output_path = os.path.join(args.exp_dir, args.output)
        df_summary.to_csv(output_path, index=False)

        if not args.quiet:
            print(f"✓ Summary saved to: {output_path}")
            print(f"✓ Total experiments: {len(df_summary)}")
            print(f"✓ Total columns: {len(df_summary.columns)}")
            print(f"\nColumn categories:")
            print(f"  - Identification: experiment_name, timestamp, folder")
            print(f"  - FL Parameters: {len([c for c in df_summary.columns if c.startswith('fl_')])} columns")
            print(f"  - Model Parameters: {len([c for c in df_summary.columns if c.startswith('model_')])} columns")
            print(f"  - Performance Metrics: loss, MAE, RMSE (best/final/avg)")
            print(f"  - Time Metrics: training time, round duration, client duration")

    return df_summary


if __name__ == "__main__":
    main()
