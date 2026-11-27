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

# Lifecycle (SITE_NETWORK_PLAN.md §4); "coming_soon"/"inactive" only appear in the sites.json fallback
SiteStatus = Literal["registered", "approved", "rejected", "active", "suspended", "revoked", "coming_soon", "inactive"]

# Kazakhstan, with a small margin (lat 40.57-55.44, lon 46.49-87.31)
KZ_LAT = (40.5, 55.5)
KZ_LON = (46.4, 87.4)
KZ_TIMEZONES = ("Asia/Almaty", "Asia/Qostanay", "Asia/Qyzylorda", "Asia/Aqtobe", "Asia/Aqtau", "Asia/Atyrau", "Asia/Oral")
DATA_SOURCES = ("csv", "opc-ua", "pi", "other")


class Site(BaseModel):
    """Public view of a site (no contact, owner or consents)."""

    id: str
    name: str
    energy_type: EnergyType
    kind: Literal["builtin", "plant"] = "builtin"
    partition_id: Optional[int] = None
    lat: float
    lon: float
    timezone: str
    capacity_kw: Optional[float] = None
    status: SiteStatus
    coordinates_source: Optional[str] = None
    # Takes part in federated training runs: lab sites with a SuperNode today; plants once their
    # Flower connection is registered (SITE_NETWORK_PLAN.md M6)
    can_train: bool = False
    train_note: Optional[str] = None   # why it can't train now (plants: SITE_NETWORK_PLAN.md §7.2)
    forecast_public: bool = True  # anyone may see its forecasts (plants: the public_forecasts consent)


class SiteListResponse(BaseModel):
    sites: List[Site]


class WindEquipment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turbine_model: str = Field(min_length=1, max_length=100)
    turbine_count: int = Field(ge=1, le=1000)
    hub_height_m: float = Field(ge=10, le=250)
    rated_power_kw: Optional[float] = Field(None, gt=0, le=20000)  # per turbine


class SolarEquipment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module_type: str = Field(min_length=1, max_length=100)
    tilt_deg: float = Field(ge=0, le=90)
    azimuth_deg: float = Field(180, ge=0, lt=360)  # 180 = facing south
    tracking: Literal["fixed", "single-axis", "dual-axis"] = "fixed"


class SiteConsents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    train: Literal[True]                 # required: the site joins federated training
    share_forecast_window: bool = False  # central forecasting from a short recent window (NFR-01 exception)
    public_forecasts: bool = False       # show this site's forecasts to viewers


class ConsentUpdate(BaseModel):
    """An operator changes participation of an approved or active plant (SITE_NETWORK_PLAN.md §4 step 6).
    train false = paused: the plant stays connected and keeps its forecasts but joins no training run."""
    model_config = ConfigDict(extra="forbid")
    train: bool
    share_forecast_window: bool
    public_forecasts: bool


class SiteRegistration(BaseModel):
    """What an operator submits for a new site (and may edit while it waits for approval)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    energy_type: EnergyType
    lat: float = Field(ge=KZ_LAT[0], le=KZ_LAT[1], description="Latitude inside Kazakhstan")
    lon: float = Field(ge=KZ_LON[0], le=KZ_LON[1], description="Longitude inside Kazakhstan")
    timezone: str = "Asia/Almaty"
    capacity_kw: float = Field(gt=0, le=5_000_000)
    equipment: Dict[str, Any]
    data_source: Literal["csv", "opc-ua", "pi", "other"] = "csv"
    contact: str = Field(min_length=3, max_length=200)
    consents: SiteConsents

    @model_validator(mode="after")
    def _check(self) -> "SiteRegistration":
        if self.timezone not in KZ_TIMEZONES:
            raise ValueError(f"timezone must be one of {list(KZ_TIMEZONES)}")
        model = SolarEquipment if self.energy_type == EnergyType.SOLAR else WindEquipment
        self.equipment = model(**self.equipment).model_dump()
        self.name = self.name.strip()
        return self


class SiteHistoryEntry(BaseModel):
    at: str
    action: str
    actor: Optional[str] = None
    note: Optional[str] = None


class SiteConnection(BaseModel):
    """What the site agent last reported (lab sites have no agent: state "lab")."""

    state: Literal["lab", "never", "online", "offline"]
    last_heartbeat_at: Optional[str] = None
    agent_kind: Optional[Literal["kit", "simulated"]] = None
    agent_version: Optional[str] = None
    last_data_hour: Optional[str] = None
    rows_today: Optional[int] = None
    gaps_today: Optional[int] = None
    heartbeat_s: int = 30
    train_hours: Optional[int] = None    # hours in the plant's training store (agent 0.2+)
    update_available: Optional[str] = None  # a newer site kit version (M8)
    quality_7d: List[Dict[str, Any]] = Field(default_factory=list)  # [{day, rows, gaps, flagged, curtailed}]


class SiteProgress(BaseModel):
    registered_at: Optional[str] = None
    approved_at: Optional[str] = None
    enrolled_at: Optional[str] = None
    online_at: Optional[str] = None


class SiteKitState(BaseModel):
    can_download: bool = False
    installed: bool = False
    token_expires_at: Optional[str] = None  # newest unused kit token


class SiteDetail(Site):
    """Full view for the owning organization and admins."""

    org_id: Optional[int] = None
    org_name: Optional[str] = None
    equipment: Dict[str, Any] = Field(default_factory=dict)
    data_source: Optional[str] = None
    contact: Optional[str] = None
    consents: Dict[str, Any] = Field(default_factory=dict)
    decision_note: Optional[str] = None
    created_at: Optional[str] = None
    decided_at: Optional[str] = None
    history: List[SiteHistoryEntry] = Field(default_factory=list)
    connection: Optional[SiteConnection] = None
    progress: Optional[SiteProgress] = None
    kit: Optional[SiteKitState] = None


class SiteDetailListResponse(BaseModel):
    sites: List[SiteDetail]


class SiteDecision(BaseModel):
    note: Optional[str] = Field(None, max_length=1000)


# ---------------------------------------------------------------------------
# Site API: what site agents send (DEMO_SIMULATION_PLAN.md §2.2)
# ---------------------------------------------------------------------------

class AgentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["kit", "simulated"] = "kit"
    version: str = Field("0.0.0", max_length=40)


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=10, max_length=200)
    agent: AgentInfo = Field(default_factory=AgentInfo)
    # Made at the plant; the private keys never leave it (SITE_NETWORK_PLAN.md §2.3)
    csr: Optional[str] = Field(None, max_length=10000)                # PEM, CN = site id
    flower_public_key: Optional[str] = Field(None, max_length=1000)  # OpenSSH EC key, registered with Flower


class HeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_kind: Literal["kit", "simulated"] = "kit"
    agent_version: str = Field("0.0.0", max_length=40)
    last_data_hour: Optional[str] = None  # ISO UTC
    rows_today: Optional[int] = Field(None, ge=0, le=100000)
    gaps_today: Optional[int] = Field(None, ge=0, le=100000)
    disk_free_gb: Optional[float] = Field(None, ge=0)
    gpu: Optional[str] = Field(None, max_length=100)
    train_hours: Optional[int] = Field(None, ge=0, le=10_000_000)   # size of the plant's training store


class RenewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csr: str = Field(min_length=100, max_length=10000)   # PEM, CN = site id, a new key made at the plant


class LocalForecastRequest(BaseModel):
    """Local mode (M7): a forecast the plant made with the downloaded model; only the forecast is sent."""
    model_config = ConfigDict(extra="forbid")
    model_version_id: int
    horizon: int = Field(ge=1, le=1000)
    issued_at: str                                    # ISO UTC, the newest observed hour
    values: List[Optional[float]] = Field(max_length=1000)   # wind speed m/s or GHI W/m2, one per hour ahead
    power_kw: Optional[List[Optional[float]]] = Field(None, max_length=1000)


class ForecastInputRequest(BaseModel):
    """The newest hours of the forecast variable (wind speed m/s, or GHI W/m2), oldest first.
    Only from sites that consented to central forecasting (SITE_NETWORK_PLAN.md §8).
    Wind height: real plants send hub height (data contract); simulated plants send NASA's 50 m."""

    model_config = ConfigDict(extra="forbid")
    end_hour: str                                                # ISO UTC hour of the last value
    values: List[Optional[float]] = Field(min_length=1, max_length=720)


class QualityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    rows: int = Field(ge=0, le=100000)
    gaps: int = Field(ge=0, le=100000)
    flagged: int = Field(0, ge=0, le=100000)
    curtailed: int = Field(0, ge=0, le=100000)


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

    energy_type: EnergyType = EnergyType.WIND
    dataset: Optional[str] = None  # default: kzmet (wind) / kzsolar (solar)
    data_source: Literal["builtin", "upload"] = "builtin"
    sites: Optional[List[str]] = None  # default: every active site of the energy type
    # Solar only (my_flower_app/solar.py): forecast the clear-sky index k* (converted back to
    # GHI) or GHI directly; leave night and low-sun hours out of the training loss.
    solar_target: Literal["kstar", "ghi"] = "kstar"
    daylight_mask: bool = True
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
        if self.sites is not None:
            if len(set(self.sites)) != len(self.sites) or not self.sites:
                raise ValueError("sites must be a non-empty list without duplicates")
            if self.min_train_clients > len(self.sites):
                raise ValueError("min_train_clients cannot exceed the number of sites")
        if self.dataset is None:
            self.dataset = "kzsolar" if self.energy_type == EnergyType.SOLAR else "kzmet"
        return self


# ---------------------------------------------------------------------------
# Runs  (plan §5.2–5.4)
# ---------------------------------------------------------------------------

RunStatus = Literal["queued", "running", "done", "failed", "stopped"]
ACTIVE_STATUSES = ("queued", "running")


class ClientRound(BaseModel):
    model_config = ConfigDict(extra="allow")

    site: str
    # rejected: the update failed the checks before aggregation (my_flower_app/robust.py), with a reason
    status: Literal["replied", "dropped", "rejected"]
    reason: Optional[str] = None
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
    # For the model card on forecasts (absent in records promoted before 2026-11-20)
    sites: List[str] = Field(default_factory=list)
    rounds_completed: Optional[int] = None
    strategy: Optional[str] = None
    promoted_by: Optional[str] = None
    # Model registry (SITE_NETWORK_PLAN.md M7); absent when the API runs without a database
    id: Optional[int] = None
    version: Optional[int] = None
    status: Optional[Literal["candidate", "promoted", "retired", "rejected"]] = None
    origin: Optional[str] = None
    model_path: Optional[str] = None      # relative to the models folder; what inference loads
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    data_percent: Optional[float] = None
    gates: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    veto_until: Optional[str] = None
    retired_at: Optional[str] = None
    note: Optional[str] = None


class ModelListResponse(BaseModel):
    models: List[RegisteredModel]


# ---------------------------------------------------------------------------
# Forecast  (plan §5.7)
# ---------------------------------------------------------------------------

class ForecastPoint(BaseModel):
    """Wind: wind_speed (m/s) + wind_power_kw. Solar: ghi + clear_sky_ghi (W/m2) + pv_power_kw."""

    timestamp: str
    wind_speed: Optional[float] = None
    wind_power_kw: Optional[float] = None
    ghi: Optional[float] = None
    clear_sky_ghi: Optional[float] = None
    pv_power_kw: Optional[float] = None
    # Filled for both energy types, so pages can lead with power
    power_kw: Optional[float] = None
    capacity_factor: Optional[float] = None  # power / capacity, 0-1


class ForecastModelRef(BaseModel):
    """The newest promoted global model that produced the forecast."""

    run_id: str
    kind: Literal["global"] = "global"
    energy_type: Optional[EnergyType] = None
    horizon: Optional[int] = None
    promoted_at: Optional[str] = None
    promoted_by: Optional[str] = None
    sites: List[str] = Field(default_factory=list)
    rounds_completed: Optional[int] = None
    strategy: Optional[str] = None
    skill_vs_persistence: Optional[float] = None
    skill_reference: Optional[str] = None
    data_percent: Optional[float] = None  # < 100: a small demo run, labelled as such
    version: Optional[int] = None         # model registry version (M7)


class ForecastResponse(BaseModel):
    energy_type: EnergyType
    site: str
    horizon: int
    unit: str = "m/s"
    as_of: str
    model: ForecastModelRef
    actual: List[ForecastPoint]
    forecast: List[ForecastPoint]
    capacity_kw: Optional[float] = None
    # "plant": the site's registered capacity; "reference": a 2 MW turbine / 1 MW PV stand-in (lab sites)
    power_basis: Literal["plant", "reference"] = "reference"
    # site_inference: lab site; central: made here from the plant's shared window; local: made at the plant
    source: Literal["site_inference", "central", "local"] = "site_inference"
    simulated: bool = False
    stored_at: Optional[str] = None       # when the stored forecast was made (M7); None = made for this request
    # FR-25: {"text", "source": "claude" | "rules", "facts"} (app/services/forecast_summary.py)
    summary: Optional[Dict[str, Any]] = None
