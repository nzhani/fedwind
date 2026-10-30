import os
import pandas as pd
import re
from pathlib import Path
from datetime import datetime


def parse_config_file(config_path):
    """Parse the config.txt file and extract parameters."""
    config_data = {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract timestamp
        timestamp_match = re.search(r'Timestamp:\s*(\S+)', content)
        if timestamp_match:
            config_data['config_timestamp'] = timestamp_match.group(1)

        # Extract Federated Learning Parameters
        fl_params = {
            'num-server-rounds': ('num_server_rounds', int),
            'fraction-train': ('fraction_train', float),
            'local-epochs': ('local_epochs', int),
            'lr': ('learning_rate', float),
            'batch-size': ('batch_size', int),
            'num-clients': ('num_clients', int)
        }

        for param, (key_name, dtype) in fl_params.items():
            pattern = rf'{param}:\s*([\d.]+)'
            match = re.search(pattern, content)
            if match:
                config_data[key_name] = dtype(match.group(1))

        # Extract Model Architecture Parameters
        model_params = {
            'seq_len': int,
            'pred_len': int,
            'patch_size': int,
            'stride': int,
            'd_model': int,
            'hidden_size': int,
            'kernel_size': int,
            'llm_layers': int,
            'lora_r': int,
            'lora_alpha': int,
            'lora_dropout': float
        }

        for param, dtype in model_params.items():
            pattern = rf'{param}:\s*([\d.]+)'
            match = re.search(pattern, content)
            if match:
                config_data[param] = dtype(match.group(1))

    except Exception as e:
        print(f"Error parsing config file {config_path}: {e}")

    return config_data


def process_experiment_folder(folder_path):
    """Process a single experiment folder and extract all data."""
    experiment_data = {}

    # Get experiment name from folder
    experiment_data['experiment_name'] = os.path.basename(folder_path)

    # Parse config.txt
    config_path = os.path.join(folder_path, 'config.txt')
    if os.path.exists(config_path):
        config_data = parse_config_file(config_path)
        experiment_data.update(config_data)
    else:
        print(f"Warning: config.txt not found in {folder_path}")

    # Read timing_summary.csv
    timing_path = os.path.join(folder_path, 'timing_summary.csv')
    if os.path.exists(timing_path):
        try:
            timing_df = pd.read_csv(timing_path)
            if not timing_df.empty:
                # Add timing data, only add prefix if column already exists
                timing_data = timing_df.iloc[0].to_dict()
                for key, value in timing_data.items():
                    # Check if column name already exists in experiment_data
                    if key in experiment_data:
                        experiment_data[f'timing_{key}'] = value
                    else:
                        experiment_data[key] = value
        except Exception as e:
            print(f"Error reading timing_summary.csv in {folder_path}: {e}")
    else:
        print(f"Warning: timing_summary.csv not found in {folder_path}")

    # Read training_summary.csv
    training_path = os.path.join(folder_path, 'training_summary.csv')
    if os.path.exists(training_path):
        try:
            training_df = pd.read_csv(training_path)
            return experiment_data, training_df
        except Exception as e:
            print(f"Error reading training_summary.csv in {folder_path}: {e}")
            return experiment_data, pd.DataFrame()
    else:
        print(f"Warning: training_summary.csv not found in {folder_path}")
        return experiment_data, pd.DataFrame()


def combine_experiments(root_folder, output_file='combined_experiments.csv'):
    """
    Combine all experiment data from subfolders into a single CSV.

    Parameters:
    - root_folder: Path to the folder containing experiment subfolders
    - output_file: Name of the output CSV file
    """
    all_data = []

    # Get all experiment folders
    experiment_folders = [f for f in Path(root_folder).iterdir()
                          if f.is_dir() and f.name.startswith('experiments_')]

    if not experiment_folders:
        print("No experiment folders found!")
        return None

    print(f"Found {len(experiment_folders)} experiment folders")

    for folder in sorted(experiment_folders):
        print(f"Processing {folder.name}...")

        # Process the experiment folder
        experiment_data, training_df = process_experiment_folder(str(folder))

        if not training_df.empty:
            # Sort by round to ensure correct order
            training_df = training_df.sort_values('round')

            # Calculate derived metrics for this experiment
            first_train_loss = None
            first_val_loss = None
            previous_train_loss = None
            previous_val_loss = None

            experiment_rows = []

            # Combine experiment metadata with each training round
            for idx, row in training_df.iterrows():
                combined_row = experiment_data.copy()
                # Add training data, only add prefix if column already exists
                for col in training_df.columns:
                    if col in combined_row:
                        combined_row[f'training_{col}'] = row[col]
                    else:
                        combined_row[col] = row[col]

                # Get current losses
                current_train_loss = row.get('train_loss')
                current_val_loss = row.get('val_loss')

                # Set first losses
                if first_train_loss is None and pd.notna(current_train_loss):
                    first_train_loss = current_train_loss
                if first_val_loss is None and pd.notna(current_val_loss):
                    first_val_loss = current_val_loss

                # Calculate loss improvements from first round
                if first_train_loss is not None and pd.notna(current_train_loss):
                    combined_row['train_loss_improvement_from_first'] = first_train_loss - current_train_loss
                    combined_row['train_loss_improvement_pct_from_first'] = ((first_train_loss - current_train_loss) / first_train_loss) * 100
                else:
                    combined_row['train_loss_improvement_from_first'] = None
                    combined_row['train_loss_improvement_pct_from_first'] = None

                if first_val_loss is not None and pd.notna(current_val_loss):
                    combined_row['val_loss_improvement_from_first'] = first_val_loss - current_val_loss
                    combined_row['val_loss_improvement_pct_from_first'] = ((first_val_loss - current_val_loss) / first_val_loss) * 100
                else:
                    combined_row['val_loss_improvement_from_first'] = None
                    combined_row['val_loss_improvement_pct_from_first'] = None

                # Calculate loss improvements from previous round
                if previous_train_loss is not None and pd.notna(current_train_loss):
                    combined_row['train_loss_improvement_from_previous'] = previous_train_loss - current_train_loss
                else:
                    combined_row['train_loss_improvement_from_previous'] = None

                if previous_val_loss is not None and pd.notna(current_val_loss):
                    combined_row['val_loss_improvement_from_previous'] = previous_val_loss - current_val_loss
                else:
                    combined_row['val_loss_improvement_from_previous'] = None

                # Time efficiency: val_loss improvement per second
                round_duration = row.get('round_duration_sec')
                if (first_val_loss is not None and pd.notna(current_val_loss) and
                    pd.notna(round_duration) and round_duration > 0):
                    total_improvement = first_val_loss - current_val_loss
                    combined_row['val_loss_improvement_per_sec'] = total_improvement / (row['round'] * round_duration)
                else:
                    combined_row['val_loss_improvement_per_sec'] = None

                # Update previous losses for next iteration
                if pd.notna(current_train_loss):
                    previous_train_loss = current_train_loss
                if pd.notna(current_val_loss):
                    previous_val_loss = current_val_loss

                experiment_rows.append(combined_row)

            # Second pass: mark best rounds
            val_losses = [row.get('val_loss') for row in experiment_rows]
            valid_val_losses = [v for v in val_losses if pd.notna(v)]
            if valid_val_losses:
                best_val_loss = min(valid_val_losses)
                for row in experiment_rows:
                    row['is_best_val_loss'] = (pd.notna(row.get('val_loss')) and
                                               row['val_loss'] == best_val_loss)
            else:
                for row in experiment_rows:
                    row['is_best_val_loss'] = False

            all_data.extend(experiment_rows)
        else:
            # If no training data, still add the experiment metadata
            all_data.append(experiment_data)

    # Create DataFrame from all collected data
    if all_data:
        result_df = pd.DataFrame(all_data)

        # Reorder columns for better readability
        # Group columns by category
        col_order = []

        # Experiment identification
        if 'experiment_name' in result_df.columns:
            col_order.append('experiment_name')
        if 'config_timestamp' in result_df.columns:
            col_order.append('config_timestamp')

        # Training round info
        training_cols = [col for col in result_df.columns if col.startswith('training_')]
        col_order.extend(sorted(training_cols))

        # Federated learning config
        fl_cols = ['num_server_rounds', 'fraction_train', 'local_epochs',
                   'learning_rate', 'batch_size', 'num_clients']
        col_order.extend([col for col in fl_cols if col in result_df.columns])

        # Model architecture
        model_cols = ['seq_len', 'pred_len', 'patch_size', 'stride', 'd_model',
                      'hidden_size', 'kernel_size', 'llm_layers', 'lora_r',
                      'lora_alpha', 'lora_dropout']
        col_order.extend([col for col in model_cols if col in result_df.columns])

        # Timing info
        timing_cols = [col for col in result_df.columns if col.startswith('timing_')]
        col_order.extend(sorted(timing_cols))

        # Add any remaining columns
        remaining_cols = [col for col in result_df.columns if col not in col_order]
        col_order.extend(remaining_cols)

        # Reorder DataFrame
        result_df = result_df[col_order]

        # Save to CSV
        result_df.to_csv(output_file, index=False)
        print(f"\nSuccessfully saved combined data to {output_file}")
        print(f"Total rows: {len(result_df)}")
        print(f"Total columns: {len(result_df.columns)}")

        return result_df
    else:
        print("No data collected!")
        return None


def print_summary(df):
    """Print a summary of the combined dataset."""
    if df is None or df.empty:
        return

    print("\n" + "=" * 60)
    print("DATASET SUMMARY")
    print("=" * 60)

    # Count unique experiments
    if 'experiment_name' in df.columns:
        unique_experiments = df['experiment_name'].nunique()
        print(f"Number of unique experiments: {unique_experiments}")

    # Show data shape
    print(f"Total rows (experiment rounds): {len(df)}")
    print(f"Total columns (features): {len(df.columns)}")

    # Show column categories
    print("\nColumn categories:")
    training_cols = [col for col in df.columns if col.startswith('training_')]
    timing_cols = [col for col in df.columns if col.startswith('timing_')]
    config_cols = [col for col in df.columns if not col.startswith('training_')
                   and not col.startswith('timing_')]

    print(f"  - Training metrics: {len(training_cols)} columns")
    print(f"  - Timing metrics: {len(timing_cols)} columns")
    print(f"  - Configuration parameters: {len(config_cols)} columns")

    # Show sample of data
    print("\nFirst few rows of combined data:")
    print(df.head())


if __name__ == "__main__":
    # Specify the path to your experiments folder
    EXPERIMENTS_FOLDER = '.'

    if not os.path.exists(EXPERIMENTS_FOLDER):
        print(f"Error: Folder '{EXPERIMENTS_FOLDER}' does not exist!")
    else:
        # Optional: Specify custom output file name
        output_name = "combined_experiments_20260315_20260316.csv"
        if not output_name:
            output_name = "combined_experiments_20251122.csv"
        elif not output_name.endswith('.csv'):
            output_name += '.csv'

        # Process all experiments
        combined_df = combine_experiments(EXPERIMENTS_FOLDER, output_name)

        # Print summary
        print_summary(combined_df)

        # Optional: Show basic statistics for numerical columns
        if combined_df is not None and not combined_df.empty:
            print("\n" + "=" * 60)
            print("BASIC STATISTICS")
            print("=" * 60)

            # Select only numerical columns for statistics
            numeric_cols = combined_df.select_dtypes(include=['float64', 'int64']).columns
            if 'training_round' in numeric_cols:
                # Show statistics for key metrics
                key_metrics = ['training_train_loss', 'training_val_loss',
                               'training_val_mae', 'training_val_rmse']
                available_metrics = [col for col in key_metrics if col in numeric_cols]

                if available_metrics:
                    print("\nKey training metrics statistics:")
                    print(combined_df[available_metrics].describe())
