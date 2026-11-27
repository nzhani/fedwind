"""
Baselines for the fall results (FR-19, DR-05, DR-07), run on exactly the windows the federated model
is tested on: the same per-site 70/10/20 split by time, the same scaler (fit on the site's train
part), the same input length and horizon, and the same metric code (run_logging.site_summary).

  persistence          last value (wind); smart persistence k* now x clear sky (solar)
  arima                ARIMA per site, fitted once on the train part, applied to every test window
  lstm_local           LSTM trained on one site only
  lstm_central         one LSTM on all sites' training data pooled (no privacy)
  lstm_fedavg          FedAvg with an LSTM, simulated in one process (same sites, rounds, local epochs)
  patchtst_local       compact PatchTST (Nie et al., 2023) trained per site
  patchtst_central     the same, pooled
  llm_local            the federated model's own architecture (frozen GPT-2 + LoRA) trained per site
  llm_central          the same architecture on pooled data

Run:  python -m baselines.run --help   (from Long-term_Forecasting/flower_app)
"""
