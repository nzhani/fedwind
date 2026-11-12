/**
 * FedWind platform API client (plan §5.7)
 *
 *   getSites()        -> GET  /api/sites
 *   getFederation()   -> GET  /api/federation
 *   listRuns()        -> GET  /api/runs
 *   getRun()          -> GET  /api/runs/{id}
 *   startRun()        -> POST /api/runs        (config JSON + optional file_<site> CSVs)
 *   stopRun()         -> POST /api/runs/{id}/stop
 *   getForecast()     -> GET  /api/forecast
 *   listModels()      -> GET  /api/models
 *   promoteModel()    -> POST /api/models/promote
 *
 * Errors keep the HTTP status so pages can tell "not connected" (503) from bad input (422).
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"

export const HORIZONS = [1, 72, 432] as const
export type Horizon = (typeof HORIZONS)[number]

export const HORIZON_LABELS: Record<Horizon, string> = {
  1: "1 hour ahead",
  72: "72 hours (3 days) ahead",
  432: "432 hours (18 days) ahead",
}

export type EnergyType = "wind" | "solar"

export const STRATEGIES = [
  { value: "fedavg", label: "FedAvg" },
  { value: "fedprox", label: "FedProx" },
  { value: "scaffold", label: "SCAFFOLD" },
  { value: "fedper", label: "FedPer" },
  { value: "fedln", label: "FedLN" },
] as const
export type Strategy = (typeof STRATEGIES)[number]["value"]

// Keys of MODEL_REGISTRY in the Flower app (LLM backbones only).
export const MODELS = [
  { value: "gpt4ts_linear", label: "GPT-2 (linear head)" },
  { value: "gpt4ts_nonlinear", label: "GPT-2 (nonlinear head)" },
  { value: "llama_linear", label: "LLaMA-160m" },
  { value: "bert_linear", label: "BERT" },
  { value: "bart_linear", label: "BART" },
  { value: "opt_linear", label: "OPT-350m" },
  { value: "gemma_linear", label: "Gemma-3 270m" },
  { value: "qwen_linear", label: "Qwen3 0.6B" },
] as const

export type RunStatus ="queued" | "running" | "done" | "failed" | "stopped"

export interface Site {
  id: string
  name: string
  energy_type: EnergyType
  partition_id: number | null
  lat: number
  lon: number
  timezone: string
  capacity_kw: number | null
  status: "active" | "coming_soon" | "inactive"
  coordinates_source: string | null
}

export interface FederationStatus {
  connected: boolean
  detail: string
  connected_nodes: number | null
}

export interface ExperimentConfig {
  sites: string[]
  strategy: Strategy
  proximal_mu: number
  rounds: number
  local_epochs: number
  min_train_clients: number
  horizon: Horizon
  seq_len: number
  data_percent: number
  model: string
  llm_layers: number
  lora_r: number
  lr: number
  batch_size: number
  dropout: number
  seed: number
}

export interface ClientRound {
  site: string
  status: "replied" | "dropped"
  num_examples?: number | null
  train_loss?: number | null
  val_mae?: number | null
}

export interface RoundMetrics {
  round: number
  total_rounds: number
  finished_at?: string | null
  duration_s?: number | null
  train_loss?: number | null
  val?: Record<string, number> | null
  val_real?: { mae?: number; rmse?: number; unit?: string } | null
  clients: ClientRound[]
  uplink_bytes?: number | null
  downlink_bytes?: number | null
}

export interface RunSummary {
  run_id: string
  status: RunStatus
  created_at: string
  strategy: string
  horizon: number
  sites: string[]
  current_round: number
  total_rounds: number
  error: string | null
}

export interface RunResult {
  status: string
  best_round?: number
  unit?: string
  metrics?: {
    normalized?: Record<string, number>
    real?: Record<string, number>
    per_site?: Record<string, Record<string, number>>
  }
  timing?: { total_s?: number; mean_round_s?: number }
  payload?: { uplink_bytes_per_client_round?: number; backbone_bytes?: number }
  [key: string]: unknown
}

export interface RunDetail extends RunSummary {
  config: Record<string, unknown>
  flower_run_id: string | null
  started_at: string | null
  finished_at: string | null
  history: RoundMetrics[]
  clients: ClientRound[]
  result: RunResult | null
}

export interface RunListResponse {
  runs: RunSummary[]
  active_run_id: string | null
}

export interface WindPoint {
  timestamp: string
  wind_speed: number
  wind_power_kw?: number | null
}

export interface ForecastResponse {
  energy_type: EnergyType
  site: string
  horizon: number
  unit: string
  as_of: string
  model: { run_id: string; kind: "global" }
  actual: WindPoint[]
  forecast: WindPoint[]
}

export interface RegisteredModel {
  energy_type: EnergyType
  horizon: number
  run_id: string
  promoted_at: string
  metrics: Record<string, unknown> | null
}

export class PlatformApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = "PlatformApiError"
  }

  /** The API is up but the federation or inference isn't connected yet. */
  get notConnected() {
    return this.status === 503
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const loc = Array.isArray(d?.loc) ? d.loc.filter((x: unknown) => x !== "body").join(".") : ""
        return loc ? `${loc}: ${d?.msg}` : String(d?.msg ?? d)
      })
      .join("; ")
  }
  return JSON.stringify(detail)
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, { cache: "no-store", ...options })
  } catch {
    throw new PlatformApiError(0, `Can't reach the API at ${API_BASE_URL}`)
  }
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail !== undefined) message = detailMessage(body.detail)
    } catch {
      // keep the status text
    }
    throw new PlatformApiError(response.status, message)
  }
  return response.json() as Promise<T>
}

export async function getSites(energyType?: EnergyType): Promise<Site[]> {
  const query = energyType ? `?energy_type=${energyType}` : ""
  return (await request<{ sites: Site[] }>(`/api/sites${query}`)).sites
}

export function getFederation(): Promise<FederationStatus> {
  return request("/api/federation")
}

export function listRuns(): Promise<RunListResponse> {
  return request("/api/runs")
}

export function getRun(runId: string): Promise<RunDetail> {
  return request(`/api/runs/${encodeURIComponent(runId)}`)
}

export function startRun(config: ExperimentConfig, files: Record<string, File> = {}): Promise<RunDetail> {
  const form = new FormData()
  form.append("config", JSON.stringify(config))
  for (const [site, file] of Object.entries(files)) {
    form.append(`file_${site}`, file)
  }
  return request("/api/runs", { method: "POST", body: form })
}

export function stopRun(runId: string): Promise<RunDetail> {
  return request(`/api/runs/${encodeURIComponent(runId)}/stop`, { method: "POST" })
}

export function getForecast(params: {
  energyType: EnergyType
  site: string
  horizon: number
  asOf?: string
}): Promise<ForecastResponse> {
  const query = new URLSearchParams({
    energy_type: params.energyType,
    site: params.site,
    horizon: String(params.horizon),
  })
  if (params.asOf) query.set("as_of", params.asOf)
  return request(`/api/forecast?${query}`)
}

export async function listModels(): Promise<RegisteredModel[]> {
  return (await request<{ models: RegisteredModel[] }>("/api/models")).models
}

export function promoteModel(runId: string): Promise<RegisteredModel> {
  return request("/api/models/promote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId }),
  })
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}
