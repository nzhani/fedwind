#!/usr/bin/env python3
"""
Plot training and validation losses from federated learning experiment.
This script creates visualizations to help identify overfitting.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import glob
from textwrap import fill
import re

def read_config_text(config_file, num_cols=3, col_padding=2, gap_width=5, divider="│"):
    """
    Multi-column aligned config with centered dividers.
    """
    if not config_file.exists():
        return "Config: Not Found"

    import re

    timestamp = None
    pairs = []

    # -------- Parse --------
    with open(config_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or set(line) == {"="}:
                continue

            if line.lower().startswith("timestamp:"):
                timestamp = line.split(":", 1)[1].strip()
                continue

            match = re.match(r"^[\s\-]*([\w\-]+)\s*:\s*(.+)$", line)
            if match:
                k, v = match.groups()
                pairs.append((k, v))

    if timestamp:
        pairs.insert(0, ("timestamp", timestamp))

    # -------- Format key = value --------
    max_key = max(len(k) for k, _ in pairs)

    formatted = [
        f"{k.ljust(max_key)} = {v}"
        for k, v in pairs
    ]

    # -------- Global width --------
    max_cell = max(len(s) for s in formatted) + col_padding

    # -------- Columns --------
    n = len(formatted)
    rows = (n + num_cols - 1) // num_cols

    columns = [
        formatted[i * rows:(i + 1) * rows]
        for i in range(num_cols)
    ]

    # Pad
    max_rows = max(len(c) for c in columns)

    for c in columns:
        c.extend([""] * (max_rows - len(c)))

    # -------- Build output --------
    lines = []

    # Gap layout: [spaces][divider][spaces]
    left_gap = gap_width // 2
    right_gap = gap_width - left_gap - 1

    gap = " " * left_gap + divider + " " * right_gap

    for r in range(max_rows):
        row = ""

        for c in range(num_cols):
            cell = columns[c][r].ljust(max_cell)
            row += cell

            if c < num_cols - 1:
                row += gap

        lines.append(row.rstrip())

    return "\n".join(lines)

def add_config_to_figure(fig, config_text, extra_space=2.0):
    """
    Add wrapped config text in a fixed-width footer box.
    Prevents left/right overflow.
    """

    # Get current size
    width, height = fig.get_size_inches()

    # Increase height
    new_height = height + extra_space
    fig.set_size_inches(width, new_height)

    # Reserve bottom space
    fig.subplots_adjust(bottom=extra_space / new_height + 0.02)

    # Create textbox area (relative coords)
    textbox_width = 0.94   # 94% of figure width
    textbox_x = (1.0 - textbox_width) / 2.0  # center the box

    fig.text(
        textbox_x,
        0.02,
        config_text,
        ha="left",
        va="bottom",
        fontsize=8,
        color="#444444",
        family="monospace",
        wrap=True,
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="#f7f7f7",
            edgecolor="#cccccc",
            alpha=0.9
        ),
        transform=fig.transFigure
    )

def add_config_and_timing(fig, config_text, timing_text, extra_space=2.0):
    """
    Add config text on the left and timing summary on the right.
    """
    width, height = fig.get_size_inches()
    new_height = height + extra_space
    fig.set_size_inches(width, new_height)
    fig.subplots_adjust(bottom=extra_space / new_height + 0.02)

    left_x = 0.04
    left_width = 0.62
    right_width = 0.15
    right_x = 1.0 - right_width - 0.04  # Position from right edge
    y = 0.02
    box_height = max(extra_space / new_height - 0.02, 0.12)

    left_ax = fig.add_axes([left_x, y, left_width, box_height])
    right_ax = fig.add_axes([right_x, y, right_width, box_height])
    left_ax.axis("off")
    right_ax.axis("off")

    left_ax.text(
        0.0,
        0.0,
        config_text,
        ha="left",
        va="bottom",
        fontsize=8,
        color="#444444",
        family="monospace",
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="#f7f7f7",
            edgecolor="#cccccc",
            alpha=0.9
        ),
        transform=left_ax.transAxes
    )

    right_ax.text(
        0.0,
        0.0,
        timing_text,
        ha="left",
        va="bottom",
        fontsize=8,
        color="#444444",
        family="monospace",
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="#f7f7f7",
            edgecolor="#cccccc",
            alpha=0.9
        ),
        transform=right_ax.transAxes
    )
def read_timing_text(timing_file):
    if not timing_file.exists():
        return "Timing: Not Found"
    timing_df = pd.read_csv(timing_file)
    if timing_df.empty:
        return "Timing: Not Found"
    timing_row = timing_df.iloc[0]
    return "\n".join([
        f"Total Training: {timing_row['total_training_time_min']:.2f} min",
        f"Avg / Round: {timing_row['avg_time_per_round_sec']:.2f} sec",
        f"Num Rounds: {int(timing_row['num_rounds'])}",
        f"Model Size: {timing_row['model_size_mb']:.2f} MB",
    ])

def annotate_points(ax, x_vals, y_vals, color, fmt="{:.2f}", fontsize=8, y_offset=5):
    for x_val, y_val in zip(x_vals, y_vals):
        ax.annotate(
            fmt.format(y_val),
            (x_val, y_val),
            textcoords="offset points",
            xytext=(0, y_offset),
            ha="center",
            va="bottom",
            color=color,
            fontsize=fontsize
        )


def plot_aggregated_losses(experiment_dir, output_dir, config_text, timing_text):
    """Plot aggregated training and validation losses across rounds."""
    # Read the training summary
    summary_path = experiment_dir / "training_summary.csv"
    if not summary_path.exists():
        print(f"  - Skipping aggregated losses (missing {summary_path.name})")
        return
    summary_df = pd.read_csv(summary_path)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Plot 1: Training vs Validation Loss
    ax1 = axes[0]
    train_line = ax1.plot(summary_df['round'], summary_df['train_loss'],
             marker='o', linewidth=2, markersize=6, label='Training Loss', color='#2E86AB')
    val_line = ax1.plot(summary_df['round'], summary_df['val_loss'],
             marker='s', linewidth=2, markersize=6, label='Validation Loss', color='#A23B72')
    ax1.set_xlabel('Round', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Loss', fontsize=12, fontweight='bold')
    ax1.set_title('Training vs Validation Loss (Aggregated)', fontsize=14, fontweight='bold')
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.set_xticks(summary_df['round'])
    annotate_points(ax1, summary_df['round'], summary_df['train_loss'], train_line[0].get_color())
    annotate_points(ax1, summary_df['round'], summary_df['val_loss'], val_line[0].get_color())

    # Plot 2: Loss Difference (Overfitting Indicator)
    ax2 = axes[1]
    loss_diff = summary_df['val_loss'] - summary_df['train_loss']
    colors = ['#D62828' if diff > 0 else '#06A77D' for diff in loss_diff]
    bars = ax2.bar(summary_df['round'], loss_diff, color=colors, alpha=0.7, edgecolor='black')
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax2.set_xlabel('Round', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Val Loss - Train Loss', fontsize=12, fontweight='bold')
    ax2.set_title('Generalization Gap (Val − Train)', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3, linestyle='--', axis='y')
    ax2.set_xticks(summary_df['round'])
    for bar in bars:
        height = bar.get_height()
        ax2.annotate(
            f"{height:.4f}",
            (bar.get_x() + bar.get_width() / 2, height),
            textcoords="offset points",
            xytext=(0, 5),
            ha="center",
            va="bottom",
            color=bar.get_facecolor(),
            fontsize=8
        )

    plt.tight_layout(rect=[0, 0.1, 1, 1])
    add_config_and_timing(fig, config_text, timing_text)
    plt.savefig(output_dir / 'aggregated_losses.png', dpi=300)
    print(f"✓ Saved: {output_dir / 'aggregated_losses.png'}")
    plt.close()

    # Print statistics
    print("\n" + "="*60)
    print("OVERFITTING ANALYSIS")
    print("="*60)
    final_round = summary_df.iloc[-1]
    print(f"Final Round ({int(final_round['round'])}):")
    print(f"  Training Loss:   {final_round['train_loss']:.6f}")
    print(f"  Validation Loss: {final_round['val_loss']:.6f}")
    print(f"  Gap (Val - Train): {final_round['val_loss'] - final_round['train_loss']:.6f}")

    if final_round['val_loss'] > final_round['train_loss']:
        gap_pct = ((final_round['val_loss'] - final_round['train_loss']) / final_round['train_loss']) * 100
        print(f"  → Overfitting detected: {gap_pct:.2f}% higher validation loss")
    else:
        print(f"  → No significant overfitting")
    print("="*60 + "\n")

def plot_client_histories(metrics_dir, output_dir, config_text, timing_text):
    """Plot individual client training histories."""
    # Find all client training history files
    client_files = sorted(glob.glob(str(metrics_dir / "client*_train_history.csv")))

    if not client_files:
        print("No client training history files found.")
        return

    num_clients = len(client_files)

    # Create subplots for each client
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    axes = axes.flatten()

    for idx, client_file in enumerate(client_files):
        df = pd.read_csv(client_file)
        client_id = df['client_id'].iloc[0]

        # Create a continuous x-axis (epoch number across all rounds)
        df['global_epoch'] = range(1, len(df) + 1)

        ax = axes[idx]
        train_line = ax.plot(df['global_epoch'], df['train_loss'],
                linewidth=1.5, label='Train Loss', color='#2E86AB', alpha=0.8)
        val_line = ax.plot(df['global_epoch'], df['val_loss'],
                linewidth=1.5, label='Val Loss', color='#A23B72', alpha=0.8)
        ax.set_xlabel('Epoch', fontsize=10)
        ax.set_ylabel('Loss', fontsize=10)
        ax.set_title(f'Client {client_id}', fontsize=11, fontweight='bold')
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, linestyle='--')
        annotate_points(ax, df['global_epoch'], df['train_loss'], train_line[0].get_color(), fontsize=6, y_offset=4)
        annotate_points(ax, df['global_epoch'], df['val_loss'], val_line[0].get_color(), fontsize=6, y_offset=4)

        # Add round boundaries
        rounds = df['round'].unique()
        for r in rounds[1:]:  # Skip first round
            first_epoch_of_round = df[df['round'] == r]['global_epoch'].iloc[0]
            ax.axvline(x=first_epoch_of_round, color='gray', linestyle=':', alpha=0.5, linewidth=1)

    # Hide extra subplots if fewer than 6 clients
    for idx in range(num_clients, len(axes)):
        axes[idx].axis('off')

    plt.suptitle('Training vs Validation Loss per Client', fontsize=16, fontweight='bold', y=0.995)
    # add_config_to_figure(fig, config_text)
    plt.tight_layout(rect=[0, 0.1, 1, 0.98])
    add_config_and_timing(fig, config_text, timing_text)
    plt.savefig(output_dir / 'client_losses.png', dpi=300)
    print(f"✓ Saved: {output_dir / 'client_losses.png'}")
    plt.close()

def plot_log_scale_comparison(experiment_dir, output_dir, config_text, timing_text):
    """Plot losses with log scale for better visibility of trends."""
    summary_path = experiment_dir / "training_summary.csv"
    if not summary_path.exists():
        print(f"  - Skipping log scale comparison (missing {summary_path.name})")
        return
    summary_df = pd.read_csv(summary_path)

    fig, ax = plt.subplots(figsize=(10, 6))

    train_line = ax.plot(summary_df['round'], summary_df['train_loss'],
            marker='o', linewidth=2, markersize=6, label='Training Loss', color='#2E86AB')
    val_line = ax.plot(summary_df['round'], summary_df['val_loss'],
            marker='s', linewidth=2, markersize=6, label='Validation Loss', color='#A23B72')
    ax.set_xlabel('Round', fontsize=12, fontweight='bold')
    ax.set_ylabel('Loss (log scale)', fontsize=12, fontweight='bold')
    ax.set_title('Training vs Validation Loss (Log Scale)', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_yscale('log')
    ax.set_xticks(summary_df['round'])
    annotate_points(ax, summary_df['round'], summary_df['train_loss'], train_line[0].get_color(), y_offset=6)
    annotate_points(ax, summary_df['round'], summary_df['val_loss'], val_line[0].get_color(), y_offset=6)
    
    # add_config_to_figure(fig, config_text)

    plt.tight_layout(rect=[0, 0.1, 1, 0.98])
    add_config_and_timing(fig, config_text, timing_text)
    plt.savefig(output_dir / 'losses_log_scale.png', dpi=300)
    print(f"✓ Saved: {output_dir / 'losses_log_scale.png'}")
    plt.close()

def run_for_experiment(experiment_dir):
    metrics_dir = experiment_dir / "metrics"
    output_dir = experiment_dir / "plots"
    output_dir.mkdir(exist_ok=True)
    config_file = experiment_dir / "config.txt"
    config_text = read_config_text(config_file, num_cols=3)
    timing_text = read_timing_text(experiment_dir / "timing_summary.csv")

    print("\n" + "="*60)
    print("FEDERATED LEARNING TRAINING ANALYSIS")
    print("="*60)
    print(f"Experiment Directory: {experiment_dir}")
    print(f"Output Directory: {output_dir}")
    print("="*60 + "\n")

    print("Generating plots...")
    plot_aggregated_losses(experiment_dir, output_dir, config_text, timing_text)
    plot_client_histories(metrics_dir, output_dir, config_text, timing_text)
    plot_log_scale_comparison(experiment_dir, output_dir, config_text, timing_text)

    print("\n" + "="*60)
    print("COMPLETE - All plots generated successfully!")
    print("="*60)
    print(f"\nView plots in: {output_dir}/")
    print("  - aggregated_losses.png    : Main training vs validation comparison")
    print("  - client_losses.png        : Individual client training histories")
    print("  - losses_log_scale.png     : Log-scale view for trend analysis")
    print("="*60 + "\n")

def main():
    base_dir = Path(__file__).parent
    experiment_dirs = sorted([p for p in base_dir.glob("experiments_*") if p.is_dir()])

    if not experiment_dirs:
        print("No experiments_* folders found. Nothing to plot.")
        return

    for experiment_dir in experiment_dirs:
        if (experiment_dir / "plots").exists():
            print(f"Skipping {experiment_dir} (plots folder already exists)")
            continue
        run_for_experiment(experiment_dir)

if __name__ == "__main__":
    main()
