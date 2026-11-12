"""
Pydantic schemas for the federated platform API (plan §5).

  /api/sites      Site registry
  /api/runs       Federated runs (experiment config, status, per-round metrics)
  /api/forecast   Per-site forecast from the current global model
  /api/models     Promoted models per (energy_type, horizon)

The legacy upload/train schemas stay in schemas.py.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


HORIZONS = (1, 72, 432)

# LLM keys of MODEL_REGISTRY in Long-term_Forecasting/flower_app/my_flower_app/task.py
MODELS = (
    "gpt4ts_linear", "gpt4ts_nonlinear", "gpt4ts_nonlinear_attnres",
    "llama_linear", "llama_nonlinear", "bert_linear", "bert_nonlinear",
    "bart_linear", "bart_nonlinear", "opt_linear", "opt_nonlinear",
    "gemma_linear", "gemma_nonlinear", "qwen_linear", "qwen_nonlinear",
)


class EnergyType(str, Enum):
    WIND = "wind"
    SOLAR = "solar"


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

class Site(BaseModel):
    id: str
    name: str
    energy_type: EnergyType
    partition_id: Optional[int] = None
    lat: float
    lon: float
    timezone: str
    capacity_kw: Optional[float] = None
    status: Literal["active", "coming_soon", "inactive"]
    coordinates_source: Optional[str] = None


class SiteListResponse(BaseModel):
    sites: List[Site]


# ---------------------------------------------------------------------------
# Experiment config  (plan §5.1)
# ---------------------------------------------------------------------------

class Strategy(str, Enum):
    FEDAVG = "fedavg"
    FEDPROX = "fedprox"
    SCAFFOLD = "scaffold"
    FEDPER = "fedper"
    FEDLN = "fedln"


class ExperimentConfig(BaseModel):
    """Experiment config sent by the experiment page and written to runs/<id>/config.yaml."""

    model_config = ConfigDict(extra="forbid")

    energy_type: Literal["wind"] = "wind"
    dataset: str = "kzmet"
    data_source: Literal["builtin", "upload"] = "builtin"
    sites: List[str] = Field(default_factory=lambda: ["almaty", "zhezkazgan", "aktau", "taraz", "aktobe"])
    mode: Literal["federated"] = "federated"
    engine: Literal["deployment"] = "deployment"
    strategy: Strategy = Strategy.FEDAVG
    proximal_mu: float = Field(0.01, ge=0)
    rounds: int = Field(20, ge=1, le=200)
    local_epochs: int = Field(2, ge=1, le=50)
    fraction_train: float = Field(1.0, gt=0, le=1)
    min_train_clients: int = Field(4, ge=1)
    round_timeout_s: int = Field(900, ge=30)
    horizon: int = 72
    seq_len: int = Field(336, ge=24, le=2048)
    data_percent: int = Field(100, ge=1, le=100)  # share of each site's train split (quick test runs)
    model: str = "gpt4ts_linear"
    llm_layers: int = Field(2, ge=1, le=12)
    peft_method: Literal["lora"] = "lora"
    lora_r: int = Field(8, ge=1, le=256)
    lora_alpha: int = Field(16, ge=1)
    is_pretrained: bool = True
    lr: float = Field(1.0e-4, gt=0)
    weight_decay: float = Field(0.01, ge=0)
    warmup_rounds: int = Field(3, ge=0)
    batch_size: int = Field(64, ge=1, le=1024)
    dropout: float = Field(0.2, ge=0, lt=1)
    seed: int = 2021
    checkpoint_every: int = Field(5, ge=1)
    resume_from: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "ExperimentConfig":
        if self.horizon not in HORIZONS:
            raise ValueError(f"horizon must be one of {list(HORIZONS)}")
        if self.model not in MODELS:
            raise ValueError(f"model must be one of {list(MODELS)}")
        if len(set(self.sites)) != len(self.sites) or not self.sites:
            raise ValueError("sites must be a non-empty list without duplicates")
        if self.min_train_clients > len(self.sites):
            raise ValueError("min_train_clients cannot exceed the number of sites")
        return self


# ---------------------------------------------------------------------------
# Runs  (plan §5.2–5.4)
# ---------------------------------------------------------------------------

RunStatus = Literal["queued", "running", "done", "failed", "stopped"]
ACTIVE_STATUSES = ("queued", "running")


class ClientRound(BaseModel):
    model_config = ConfigDict(extra="allow")

    site: str
    status: Literal["replied", "dropped"]
    num_examples: Optional[int] = None
    train_loss: Optional[float] = None
    val_mae: Optional[float] = None


class RoundMetrics(BaseModel):
    """One line of metrics.jsonl, written by the ServerApp after every round."""

    model_config = ConfigDict(extra="allow")

    round: int
    total_rounds: int
    finished_at: Optional[str] = None
    duration_s: Optional[float] = None
    train_loss: Optional[float] = None
    val: Optional[Dict[str, float]] = None
    val_real: Optional[Dict[str, Any]] = None
    clients: List[ClientRound] = Field(default_factory=list)
    uplink_bytes: Optional[int] = None
    downlink_bytes: Optional[int] = None


class RunSummary(BaseModel):
    run_id: str
    status: RunStatus
    created_at: str
    strategy: str
    horizon: int
    sites: List[str]
    current_round: int = 0
    total_rounds: int
    error: Optional[str] = None


class RunDetail(RunSummary):
    config: Dict[str, Any]
    flower_run_id: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    history: List[RoundMetrics] = Field(default_factory=list)
    clients: List[ClientRound] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None


class RunListResponse(BaseModel):
    runs: List[RunSummary]
    active_run_id: Optional[str] = None


class FederationStatus(BaseModel):
    connected: bool
    detail: str
    connected_nodes: Optional[int] = None


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PromoteRequest(BaseModel):
    run_id: str


class RegisteredModel(BaseModel):
    energy_type: EnergyType
    horizon: int
    run_id: str
    promoted_at: str
    metrics: Optional[Dict[str, Any]] = None


class ModelListResponse(BaseModel):
    models: List[RegisteredModel]


# ---------------------------------------------------------------------------
# Forecast  (plan §5.7)
# ---------------------------------------------------------------------------

class WindPoint(BaseModel):
    timestamp: str
    wind_speed: float
    wind_power_kw: Optional[float] = None


class ForecastModelRef(BaseModel):
    run_id: str
    kind: Literal["global"] = "global"


class ForecastResponse(BaseModel):
    energy_type: EnergyType
    site: str
    horizon: int
    unit: str = "m/s"
    as_of: str
    model: ForecastModelRef
    actual: List[WindPoint]
    forecast: List[WindPoint]
