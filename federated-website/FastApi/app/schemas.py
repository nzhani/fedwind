"""
Pydantic schemas for request/response validation.

Defines the contract between:
  - Frontend -> FastAPI  (request schemas)
  - FastAPI -> Frontend  (response schemas)
  - FastAPI -> Training module (internal schemas)

CSV Format (NASA POWER hourly data):
  YEAR, MO, DY, HR, WS50M
  2026,  1,  1,  0,  8.65
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class TrainingModelName(str, Enum):
    GPT4TS = "GPT4TS"
    GPT4TS_LINEAR = "GPT4TS_LINEAR"
    LLAMA = "LLAMA"
    LLAMA_LINEAR = "LLAMA_LINEAR"
    BERT = "BERT"
    BERT_LINEAR = "BERT_LINEAR"
    BART = "BART"
    BART_LINEAR = "BART_LINEAR"
    OPT = "OPT"
    OPT_LINEAR = "OPT_LINEAR"
    GEMMA = "GEMMA"
    GEMMA_LINEAR = "GEMMA_LINEAR"
    QWEN = "QWEN"
    QWEN_LINEAR = "QWEN_LINEAR"


class TrainingMode(str, Enum):
    CENTRALIZED = "centralized"
    FEDERATED = "federated"


VALID_PREDICTION_LENGTHS = [1, 72, 432]


# ---------------------------------------------------------------------------
# Request schemas  (Frontend -> FastAPI)
# ---------------------------------------------------------------------------

class FederatedAlgorithm(str, Enum):
    FEDAVG = "FedAvg"
    FEDPROX = "FedProx"
    SCAFFOLD = "SCAFFOLD"
    STATAVG = "StatAvg"
    FEDPER = "FedPer"
    FEDLN = "FedLN"


class TrainingConfig(BaseModel):
    """
    Training configuration sent alongside file upload.
    Maps 1-to-1 with dashboard form fields.
    """
    training_model: TrainingModelName = Field(
        default=TrainingModelName.GPT4TS,
        description="LLM backbone: GPT4TS | LLAMA | BERT | BART",
    )
    prediction_length: int = Field(
        default=6,
        description="Forecast horizon in hourly steps",
    )
    dropout_rate: float = Field(
        default=0.2,
        ge=0.0,
        le=0.5,
        description="Dropout regularization (0.0 - 0.5)",
    )
    mode: TrainingMode = Field(
        default=TrainingMode.CENTRALIZED,
        description="centralized or federated",
    )
    # Federated-only fields (ignored in centralized mode)
    federated_algorithm: FederatedAlgorithm = Field(
        default=FederatedAlgorithm.FEDAVG,
        description="Federated aggregation algorithm",
    )
    num_clients: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of participating federated clients",
    )
    num_rounds: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of federated communication rounds",
    )
    local_epochs: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Local training epochs per round",
    )
    llm_layers: int = Field(
        default=4,
        ge=1,
        le=12,
        description="Number of LLM transformer layers",
    )
    # Federated advanced params
    proximal_mu: Optional[float] = Field(default=None, description="FedProx proximal term mu")
    # Centralized advanced params (optional, have sensible defaults)
    learning_rate: Optional[float] = Field(default=None, description="Learning rate override")
    batch_size: Optional[int] = Field(default=None, description="Batch size override")
    seq_len: Optional[int] = Field(default=None, description="Input sequence length override")
    epochs: Optional[int] = Field(default=None, description="Training epochs override")
    weight_decay: Optional[float] = Field(default=None, description="Weight decay override")
    warmup_rounds: Optional[int] = Field(default=None, description="Warmup rounds override")
    patch_size: Optional[int] = Field(default=None, description="Patch size override")
    patch_stride: Optional[int] = Field(default=None, description="Patch stride override")
    hidden_size: Optional[int] = Field(default=None, description="Hidden size override")
    kernel_size: Optional[int] = Field(default=None, description="Kernel size override")


# ---------------------------------------------------------------------------
# Response schemas  (FastAPI -> Frontend)
# ---------------------------------------------------------------------------

class FileInfo(BaseModel):
    """Metadata about a single uploaded file."""
    filename: str
    original_name: str
    size_bytes: int
    rows: int
    columns: int
    column_names: List[str]
    preview: List[Dict[str, Any]]


class UploadResponse(BaseModel):
    """Returned after POST /api/upload."""
    success: bool
    message: str
    file: FileInfo


class TrainingMetrics(BaseModel):
    """Evaluation metrics returned from the training module."""
    mae: float = Field(description="Mean Absolute Error")
    rmse: float = Field(description="Root Mean Squared Error")


class ForecastPoint(BaseModel):
    """A single timestamp in the forecast output."""
    step: int
    timestamp: Optional[str] = None
    actual: Optional[float] = None
    predicted: float


class TrainingResult(BaseModel):
    """
    Returned after POST /api/train.
    This is what the frontend renders in the results panel.
    """
    success: bool
    message: str
    model_name: str
    prediction_length: int
    dropout_rate: float
    training_time_seconds: float
    metrics: TrainingMetrics
    forecast: List[ForecastPoint]
    download_training_summary: Optional[str] = None   # URL path
    download_timing_summary:   Optional[str] = None   # URL path


class TrainRequest(BaseModel):
    """
    Body for POST /api/train.
    References a previously uploaded file plus config.
    """
    filename: str = Field(description="Saved filename from upload response")
    config: TrainingConfig


class FileListItem(BaseModel):
    """Single file entry in the file list response."""
    filename: str
    size: int
    modified: str


class FileListResponse(BaseModel):
    """Returned by GET /api/files."""
    files: List[FileListItem]
    total: int


class HealthResponse(BaseModel):
    """Returned by GET /health."""
    status: str
    version: str
    environment: str
    timestamp: str
    services: Dict[str, str]


# ---------------------------------------------------------------------------
# Internal schemas  (FastAPI service -> Training module)
# ---------------------------------------------------------------------------

class TrainingInput(BaseModel):
    """
    Structured input passed from the service layer to the
    centralized training module.  This is the bridge object.
    """
    csv_path: str = Field(description="Absolute path to the saved CSV file")
    model_name: str = Field(description="GPT4TS | LLAMA | BERT | BART")
    prediction_length: int = Field(description="Forecast horizon (steps)")
    dropout_rate: float = Field(description="Dropout for regularization")
    # Defaults used by the training repo
    seq_len: int = Field(default=336, description="Input sequence length")
    batch_size: int = Field(default=64, description="Training batch size")
    learning_rate: float = Field(default=0.0001329291894316216, description="Learning rate")
    epochs: int = Field(default=20, description="Training epochs")
    llm_layers: int = Field(default=2, description="Number of LLM layers")
    weight_decay: float = Field(default=0.0004335281794951569, description="Weight decay")
    warmup_rounds: int = Field(default=3, description="Warmup rounds")
    patch_size: int = Field(default=16, description="Patch size")
    patch_stride: int = Field(default=16, description="Patch stride")
    hidden_size: int = Field(default=80, description="Hidden size")
    kernel_size: int = Field(default=7, description="Kernel size")


class TrainingOutput(BaseModel):
    """
    Structured output returned by the centralized training module.
    The service layer converts this into TrainingResult for the frontend.
    """
    mae: float
    rmse: float
    # mape intentionally omitted
    training_time_seconds: float
    predictions: List[float]
    actuals: Optional[List[float]] = None
    exp_dir: Optional[str] = None     


class FederatedTrainingInput(BaseModel):
    """
    Structured input passed from the service layer to the
    federated training module.  Mirrors TrainingInput but adds
    federated-specific parameters.
    """
    csv_path: str = Field(description="Absolute path to the saved CSV file")
    model_name: str = Field(description="GPT4TS | LLAMA | BERT | BART")
    prediction_length: int = Field(description="Forecast horizon (steps)")
    dropout_rate: float = Field(description="Dropout for regularization")
    federated_algorithm: str = Field(
        default="FedAvg",
        description="FedAvg | FedProx | FedBN | FedPer | SCAFFOLD",
    )
    num_clients: int = Field(default=5, description="Number of federated clients")
    # Defaults matching the training repo
    seq_len: int = Field(default=336, description="Input sequence length")
    batch_size: int = Field(default=32, description="Training batch size")
    learning_rate: float = Field(default=0.0001, description="Learning rate")
    rounds: int = Field(default=5, description="Federated communication rounds")
    local_epochs: int = Field(default=1, description="Local training epochs per round")
    llm_layers: int = Field(default=4, description="Number of LLM layers to use")
    proximal_mu: Optional[float] = Field(default=None, description="FedProx proximal term mu")
    weight_decay: Optional[float] = Field(default=None, description="Weight decay")
    warmup_rounds: Optional[int] = Field(default=None, description="Warmup rounds")
    patch_size: Optional[int] = Field(default=None, description="Patch size")
    patch_stride: Optional[int] = Field(default=None, description="Patch stride")
    hidden_size: Optional[int] = Field(default=None, description="Hidden size")
    kernel_size: Optional[int] = Field(default=None, description="Kernel size")


class FederatedTrainingOutput(BaseModel):
    """
    Structured output returned by the federated training module.
    Same shape as TrainingOutput so the service layer can handle
    both modes uniformly.
    """
    mae: float
    rmse: float
    mape: Optional[float] = None
    training_time_seconds: float
    predictions: List[float]
    actuals: Optional[List[float]] = None
    best_round: Optional[int] = None
    exp_dir: Optional[str] = None
    num_clients: Optional[int] = None
    federated_algorithm: Optional[str] = None
