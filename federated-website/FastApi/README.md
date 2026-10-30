# FedWind API Backend

FastAPI backend for the Federated Learning Wind Speed Forecasting System.

Architecture: **Router -> Service -> Training Client (external repo)**

---

## Folder Structure

```
fastapi/
├── main.py                          # App entry point, CORS, routers
├── requirements.txt                 # Python dependencies
├── uploads/                         # Uploaded CSV files (auto-created)
├── models/                          # Saved model weights (auto-created)
├── feedback/                        # Saved feedback entries (auto-created)
└── app/
    ├── __init__.py
    ├── schemas.py                   # All Pydantic models (request/response)
    ├── routers/
    │   ├── __init__.py
    │   ├── health.py                # GET  /health
    │   ├── upload.py                # POST /api/upload, GET/DELETE /api/files
    │   ├── train.py                 # POST /api/train
    │   ├── federated.py             # Federated learning endpoints
    │   └── feedback.py              # POST /api/feedback
    └── services/
        ├── __init__.py
        ├── training_service.py      # Orchestration: validate -> build input -> call client
        ├── training_client.py       # Bridge to external training repo (STUB)
        └── telegram_service.py      # Sends developer feedback to Telegram group
```

---

## Data Flow (Centralized Training)

```
Frontend (Dashboard)
  │
  │  1. POST /api/upload  (CSV file)
  │     <- { file: { filename, rows, columns, preview } }
  │
  │  2. POST /api/train   (filename + config)
  │     -> { filename, config: { training_model, prediction_length, dropout_rate, mode } }
  │
  ▼
Router (train.py)
  │
  ▼
Service (training_service.py)
  │  - Validates CSV columns (YEAR, MO, DY, HR, WS50M)
  │  - Validates config ranges
  │  - Builds TrainingInput object
  │
  ▼
Training Client (training_client.py)    <-- REPLACE THIS WITH YOUR REPO
  │  - Calls your centralized training function
  │  - Returns TrainingOutput (mae, rmse, mape, predictions, actuals)
  │
  ▼
Service converts to TrainingResult
  │
  ▼
Frontend receives:
  { metrics: { mae, rmse, mape }, forecast: [{ step, predicted, actual }] }
```

---

## API Endpoints

| Method | Endpoint              | Description                       |
|--------|-----------------------|-----------------------------------|
| GET    | `/health`             | Health check                      |
| POST   | `/api/upload`         | Upload a CSV file                 |
| GET    | `/api/files`          | List uploaded files               |
| DELETE | `/api/files/{name}`   | Delete a file                     |
| POST   | `/api/train`          | Start centralized training        |
| POST   | `/api/feedback`       | Submit user feedback to developers|

---

## Telegram Feedback Reply Flow

The project supports this full feedback flow:

1. A user sends a question from the website
2. The backend saves it in `feedback/user_feedback.jsonl`
3. The backend forwards it to the Telegram developer/support group
4. A developer replies in Telegram
5. The backend saves that reply as the official answer
6. The answer appears in the website's `Recent Answers` section

### How developers should answer in Telegram

When the bot posts a new website question in the Telegram group:

- You must use Telegram's **Reply** feature on that exact bot message
- Your reply must start with `ANSWER:`

Example:

ANSWER: Please upload one CSV file at a time.
---

## Environment Variables

Create a `.env` file in the `fastapi/` root directory with:

```env
BOT_TOKEN=your_telegram_bot_token
SUPPORT_CHAT_ID=your_telegram_group_chat_id
```
---

## Quick Start

```bash
cd fastapi
python -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Docs: http://localhost:8001/docs

---

## CSV Format (NASA POWER Hourly Data)

```csv
YEAR,MO,DY,HR,WS50M
2026,1,1,0,8.65
2026,1,1,1,8.42
2026,1,1,2,7.55
```

- `WS50M` = Wind Speed at 10 meters (m/s)
- Hourly resolution
- Source: NASA POWER Data Access Viewer

---

## Example API Calls

### Upload a CSV

```bash
curl -X POST http://localhost:8001/api/upload \
  -F "file=@POWER_Hourly_Data.csv"
```

Response:
```json
{
  "success": true,
  "message": "File 'POWER_Hourly_Data.csv' uploaded successfully",
  "file": {
    "filename": "20260213_143022_POWER_Hourly_Data.csv",
    "original_name": "POWER_Hourly_Data.csv",
    "size_bytes": 18830,
    "rows": 1056,
    "columns": 5,
    "column_names": ["YEAR", "MO", "DY", "HR", "WS50M"],
    "preview": [{"YEAR": "2026", "MO": "1", "DY": "1", "HR": "0", "WS50M": "8.65"}]
  }
}
```

### Start Training

```bash
curl -X POST http://localhost:8001/api/train \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "20260213_143022_POWER_Hourly_Data.csv",
    "config": {
      "training_model": "GPT4TS",
      "prediction_length": 6,
      "dropout_rate": 0.2,
      "mode": "centralized"
    }
  }'
```

Response:
```json
{
  "success": true,
  "message": "Training complete using GPT4TS with 6-step horizon",
  "model_name": "GPT4TS",
  "prediction_length": 6,
  "dropout_rate": 0.2,
  "training_time_seconds": 3.21,
  "metrics": {
    "mae": 0.6757,
    "rmse": 0.8863,
    "mape": 5.8
  },
  "forecast": [
    {"step": 1, "predicted": 8.12, "actual": 8.20},
    {"step": 2, "predicted": 8.35, "actual": 8.50}
  ]
}
```

---

## Integrating Your Centralized Training Repo

The file `app/services/training_client.py` contains a **mock stub** that you
must replace with your actual training code.

### Option A: pip install (recommended)

```bash
# In your training repo, make it installable:
pip install -e /path/to/centralized-training-repo

# Then in training_client.py, replace the mock with:
from centralized_training.run import train_centralized
```

### Option B: sys.path (quick dev setup)

```python
# In training_client.py:
import sys
sys.path.insert(0, "/path/to/centralized-training-repo")
from run_centralized import train_centralized
```

### Expected Function Signature

Your training repo should expose a function like this:

```python
def train_centralized(
    csv_path: str,
    model_name: str,        # "GPT4TS" | "LLAMA" | "BERT" | "BART"
    pred_len: int,          # 1, 3, 6, 36, 72, 144, 432
    dropout: float,         # 0.0 - 0.5
    seq_len: int = 336,
    batch_size: int = 32,
    lr: float = 0.0001,
    epochs: int = 10,
) -> dict:
    """
    Returns:
    {
        "mae": 0.6757,
        "rmse": 0.8863,
        "mape": 5.8,
        "training_time_seconds": 42.5,
        "predictions": [8.1, 8.3, ...],   # length = pred_len
        "actuals":     [8.2, 8.5, ...],   # optional
    }
    """
```

### Where to Make the Change

Edit **one file only**: `app/services/training_client.py`

Replace the mock body of `run_centralized_training()` with:

```python
def run_centralized_training(inp: TrainingInput) -> TrainingOutput:
    from centralized_training.run import train_centralized  # your repo

    result = train_centralized(
        csv_path=inp.csv_path,
        model_name=inp.model_name,
        pred_len=inp.prediction_length,
        dropout=inp.dropout_rate,
        seq_len=inp.seq_len,
        batch_size=inp.batch_size,
        lr=inp.learning_rate,
        epochs=inp.epochs,
    )
    return TrainingOutput(**result)
```

Everything else (router, service, schemas, frontend) stays the same.

---

## Configuration Defaults

| Parameter          | Default  | Options                          |
|--------------------|----------|----------------------------------|
| Training Model     | GPT4TS   | GPT4TS, LLAMA, BERT, BART       |
| Prediction Length   | 6        | 1, 3, 6, 36, 72, 144, 432       |
| Dropout Rate       | 0.2      | 0.0 - 0.5                       |
| Sequence Length     | 336      | (internal, not exposed in UI)    |
| Batch Size          | 32       | (internal)                       |
| Learning Rate       | 0.0001   | (internal)                       |
| Epochs              | 10       | (internal)                       |

---

## CORS

Allows requests from `localhost:3001` (Next.js) and `localhost:5173` (Vite).
For production, restrict origins in `main.py`.

## License

Academic research project - Nazarbayev University, CSCI 408.
