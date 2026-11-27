/**
 * ArqauQuat platform API client (plan §5.7)
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

// Empty: the API on this website's own address (/api, forwarded by next.config.mjs)
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "")

export const HORIZONS = [1, 72, 432] as const
export type Horizon = (typeof HORIZONS)[number]

export const HORIZON_LABELS: Record<Horizon, string> = {
  1: "1 hour ahead",
  72: "72 hours (3 days) ahead",
  432: "432 hours (18 days) ahead",
}

export type EnergyType = "wind" | "solar"

export const ENERGY_TYPES: { value: EnergyType; label: string; quantity: string; unit: string }[] = [
  { value: "wind", label: "Wind", quantity: "Wind speed", unit: "m/s" },
  { value: "solar", label: "Solar", quantity: "Irradiance (GHI)", unit: "W/m²" },
]

export const SOLAR_TARGETS = [
  { value: "kstar", label: "Clear-sky index k* (recommended)" },
  { value: "ghi", label: "GHI directly" },
] as const
export type SolarTarget = (typeof SOLAR_TARGETS)[number]["value"]

/** "W/m2" from the API -> "W/m²" for display. */
export function displayUnit(unit: string | null | undefined): string {
  if (!unit) return ""
  return unit === "W/m2" ? "W/m²" : unit
}

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

export type SiteStatus = "registered" | "approved" | "rejected" | "active" | "suspended" | "revoked" | "coming_soon" | "inactive"

export interface Site {
  id: string
  name: string
  energy_type: EnergyType
  kind: "builtin" | "plant"
  partition_id: number | null
  lat: number
  lon: number
  timezone: string
  capacity_kw: number | null
  status: SiteStatus
  coordinates_source: string | null
  /** Active and connected to Flower: the only sites a training run can use (plants: M6). */
  can_train?: boolean
  /** Anyone may see its forecasts: lab sites, and plants that consented to public forecasts */
  forecast_public?: boolean
}

export interface WindEquipment {
  turbine_model: string
  turbine_count: number
  hub_height_m: number
  rated_power_kw?: number | null
}

export interface SolarEquipment {
  module_type: string
  tilt_deg: number
  azimuth_deg: number
  tracking: "fixed" | "single-axis" | "dual-axis"
}

export interface SiteConsents {
  train: boolean
  share_forecast_window?: boolean
  public_forecasts?: boolean
}

export interface SiteRegistration {
  name: string
  energy_type: EnergyType
  lat: number
  lon: number
  timezone: string
  capacity_kw: number
  equipment: WindEquipment | SolarEquipment
  data_source: "csv" | "opc-ua" | "pi" | "other"
  contact: string
  consents: SiteConsents
}

export interface SiteDetail extends Site {
  org_id: number | null
  org_name: string | null
  equipment: Record<string, unknown>
  data_source: string | null
  contact: string | null
  consents: Record<string, unknown>
  decision_note: string | null
  created_at: string | null
  decided_at: string | null
  history: { at: string; action: string; actor: string | null; note: string | null }[]
  connection?: SiteConnection | null
  progress?: SiteProgress | null
  kit?: SiteKitState | null
}

export interface QualityDay {
  day: string
  rows: number
  gaps: number
  flagged: number
  curtailed: number
}

/** Live link to the site agent: online if the last heartbeat is younger than 3 × heartbeat_s. */
export interface SiteConnection {
  state: "lab" | "never" | "online" | "offline"
  last_heartbeat_at?: string | null
  agent_kind?: "kit" | "simulated" | null
  agent_version?: string | null
  last_data_hour?: string | null
  rows_today?: number | null
  gaps_today?: number | null
  heartbeat_s: number
  /** Hours in the plant's training store (agent 0.2+) */
  train_hours?: number | null
  /** A newer site kit version (M8) */
  update_available?: string | null
  quality_7d?: QualityDay[]
}

export interface SiteProgress {
  registered_at?: string | null
  approved_at?: string | null
  enrolled_at?: string | null
  online_at?: string | null
}

export interface SiteKitState {
  can_download: boolean
  installed: boolean
  token_expires_at?: string | null
}

export type SiteAction = "approve" | "reject" | "suspend" | "resume" | "revoke"

/** Kazakhstan bounds the API accepts (with a small margin). */
export const KZ_BOUNDS = { lat: [40.5, 55.5], lon: [46.4, 87.4] } as const
export const KZ_TIMEZONES = ["Asia/Almaty", "Asia/Qostanay", "Asia/Qyzylorda", "Asia/Aqtobe", "Asia/Aqtau", "Asia/Atyrau", "Asia/Oral"] as const
export const DATA_SOURCES = [
  { value: "csv", label: "CSV export into a folder" },
  { value: "opc-ua", label: "OPC UA server" },
  { value: "pi", label: "AVEVA/OSIsoft PI" },
  { value: "other", label: "Other" },
] as const

export interface FederationStatus {
  connected: boolean
  detail: string
  connected_nodes: number | null
}

export interface ExperimentConfig {
  energy_type: EnergyType
  sites: string[]
  solar_target?: SolarTarget
  daylight_mask?: boolean
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
  /** rejected: the update failed the checks before aggregation (reason says why) */
  status: "replied" | "dropped" | "rejected"
  reason?: string | null
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
  energy_type?: EnergyType
  metrics?: {
    normalized?: Record<string, number>
    /** Numbers, plus power_basis (text) and by_lead ({"1"|"6"|"24": {mae, rmse, skill}}) from newer runs */
    real?: Record<string, unknown>
    per_site?: Record<string, Record<string, unknown>>
    reference?: string
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

/** Wind points: wind_speed (m/s) + wind_power_kw. Solar points: ghi + clear_sky_ghi (W/m²) + pv_power_kw. */
export interface ForecastPoint {
  timestamp: string
  wind_speed?: number | null
  wind_power_kw?: number | null
  ghi?: number | null
  clear_sky_ghi?: number | null
  pv_power_kw?: number | null
  /** Power of the plant (or the reference turbine / PV for lab sites), kW */
  power_kw?: number | null
  /** power / capacity, 0-1 */
  capacity_factor?: number | null
}

/** The forecast quantity of a point: wind speed or GHI. */
export function pointValue(p: ForecastPoint, energyType: EnergyType): number | null {
  return (energyType === "solar" ? p.ghi : p.wind_speed) ?? null
}

/** Power of a point in kW: turbine power or PV power. */
export function pointPower(p: ForecastPoint, energyType: EnergyType): number | null {
  return p.power_kw ?? (energyType === "solar" ? p.pv_power_kw : p.wind_power_kw) ?? null
}

/** Energy type of a run from its config (runs before solar existed are wind). */
export function runEnergyType(config: Record<string, unknown> | null | undefined): EnergyType {
  return config?.energy_type === "solar" ? "solar" : "wind"
}

/** The model behind a forecast: always the newest promoted run for that energy type and horizon. */
export interface ForecastModelRef {
  run_id: string
  kind: "global"
  energy_type?: EnergyType | null
  horizon?: number | null
  promoted_at?: string | null
  promoted_by?: string | null
  sites: string[]
  rounds_completed?: number | null
  strategy?: string | null
  skill_vs_persistence?: number | null
  skill_reference?: string | null
  /** Share of the training data the run used; below 100 it is a small demo run */
  data_percent?: number | null
  /** Model registry version (M7) */
  version?: number | null
}

export interface ForecastResponse {
  energy_type: EnergyType
  site: string
  horizon: number
  unit: string
  as_of: string
  model: ForecastModelRef
  actual: ForecastPoint[]
  forecast: ForecastPoint[]
  capacity_kw?: number | null
  /** "plant": the site's registered capacity; "reference": 2 MW turbine / 1 MW PV (lab sites) */
  power_basis: "plant" | "reference"
  /** site_inference: lab site; central: made here from the plant's shared window; local: made at the plant */
  source: "site_inference" | "central" | "local"
  simulated: boolean
  /** When the stored forecast was made; null = made for this request */
  stored_at?: string | null
  /** FR-25: short text summary; source "claude" when Claude worded it, "rules" for the fixed template */
  summary?: { text: string; source: "claude" | "rules" } | null
}

export interface RegisteredModel {
  energy_type: EnergyType
  horizon: number
  run_id: string
  promoted_at: string
  metrics: Record<string, unknown> | null
  sites?: string[]
  rounds_completed?: number | null
  strategy?: string | null
  promoted_by?: string | null
  // Model registry (M7)
  id?: number | null
  version?: number | null
  status?: "candidate" | "promoted" | "retired" | "rejected" | null
  origin?: "manual" | "schedule" | "import" | null
  model_path?: string | null
  sha256?: string | null
  size_bytes?: number | null
  data_percent?: number | null
  gates?: { passed: boolean; gates: { name: string; passed: boolean; detail: string }[]; compared_with?: number | null } | null
  created_at?: string | null
  veto_until?: string | null
  retired_at?: string | null
  note?: string | null
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

// CSRF token of the current session (from GET /api/auth/me), sent with state-changing requests.
let csrfToken: string | null = null
export function setCsrfToken(token: string | null) {
  csrfToken = token
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase()
  const headers = new Headers(options.headers)
  if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRF-Token", csrfToken)
  let response: Response
  try {
    // credentials: the session cookie (httpOnly) goes with every call
    response = await fetch(`${API_BASE_URL}${endpoint}`, { cache: "no-store", credentials: "include", ...options, headers })
  } catch {
    throw new PlatformApiError(0, `Can't reach the API${API_BASE_URL ? ` at ${API_BASE_URL}` : ""}`)
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

export function listModelVersions(): Promise<RegisteredModel[]> {
  return request("/api/models/versions")
}

export function promoteModelVersion(id: number, note?: string): Promise<RegisteredModel> {
  return request(`/api/models/versions/${id}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note: note ?? null }),
  })
}

export function vetoModelVersion(id: number, note: string): Promise<RegisteredModel> {
  return request(`/api/models/versions/${id}/veto`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  })
}

export function promoteModel(runId: string): Promise<RegisteredModel> {
  return request("/api/models/promote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId }),
  })
}

// ---------------------------------------------------------------------------
// Accounts (SITE_NETWORK_PLAN.md §3)
// ---------------------------------------------------------------------------

export type Role = "admin" | "operator" | "viewer"

export interface AccountUser {
  id: number
  email: string
  name: string
  role: Role
  organization: { id: number; name: string } | null
  active: boolean
}

export interface SessionInfo {
  user: AccountUser
  csrf_token: string
  expires_at: string
}

export interface AuditEntry {
  id: number
  at: string
  actor_type: string
  actor_id: string | null
  /** The user's name when a person did it */
  actor_name?: string | null
  action: string
  target: string | null
  details: Record<string, unknown>
  ip: string | null
}

/** The current session, or null when not logged in. */
export async function getMe(): Promise<SessionInfo | null> {
  try {
    return await request<SessionInfo>("/api/auth/me")
  } catch (err) {
    if (err instanceof PlatformApiError && err.status === 401) return null
    throw err
  }
}

const json = (body: unknown): RequestInit => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
})

export function login(email: string, password: string): Promise<SessionInfo> {
  return request("/api/auth/login", { method: "POST", ...json({ email, password }) })
}

export function registerOperator(body: { email: string; password: string; name: string; organization: string }): Promise<SessionInfo> {
  return request("/api/auth/register", { method: "POST", ...json(body) })
}

export function logout(): Promise<{ ok: boolean }> {
  return request("/api/auth/logout", { method: "POST" })
}

export async function listUsers(): Promise<AccountUser[]> {
  return (await request<{ users: AccountUser[] }>("/api/admin/users")).users
}

export function createUser(body: { email: string; password: string; name: string; role: Role; organization?: string }): Promise<AccountUser> {
  return request("/api/admin/users", { method: "POST", ...json(body) })
}

export function updateUser(id: number, patch: { role?: Role; active?: boolean }): Promise<AccountUser> {
  return request(`/api/admin/users/${id}`, { method: "PATCH", ...json(patch) })
}

export interface AuditPage {
  entries: AuditEntry[]
  next_before: number | null
}

export function getAuditPage(filters: { limit?: number; action?: string; target?: string; actor?: string; before?: number | null } = {}): Promise<AuditPage> {
  const q = new URLSearchParams({ limit: String(filters.limit ?? 50) })
  if (filters.action) q.set("action", filters.action)
  if (filters.target) q.set("target", filters.target)
  if (filters.actor) q.set("actor", filters.actor)
  if (filters.before) q.set("before", String(filters.before))
  return request(`/api/admin/audit?${q}`)
}

export async function getAudit(limit = 100): Promise<AuditEntry[]> {
  return (await getAuditPage({ limit })).entries
}

export interface AttentionItem {
  kind: "approval" | "offline" | "failed_run"
  site_id?: string
  run_id?: string
  title: string
  since: string | null
  link: string
}

export interface AdminOverview {
  tiles: {
    waiting: number
    active_sites: number
    online_now: number
    users: number
    run: { run_id: string; status: RunStatus; current_round: number; total_rounds: number } | null
  }
  attention: AttentionItem[]
  recent: AuditEntry[]
}

export interface HealthCheck {
  name: string
  status: "ok" | "warn" | "error"
  detail: string
}

export interface HealthReport {
  status: "ok" | "warn" | "error"
  checked_at: string
  checks: HealthCheck[]
}

export function getHealthReport(): Promise<HealthReport> {
  return request("/api/admin/health")
}

export function getAdminOverview(): Promise<AdminOverview> {
  return request("/api/admin/overview")
}

// ---------------------------------------------------------------------------
// Site registration (SITE_NETWORK_PLAN.md §4)
// ---------------------------------------------------------------------------

export function registerSite(body: SiteRegistration): Promise<SiteDetail> {
  return request("/api/sites", { method: "POST", ...json(body) })
}

export async function listMySites(): Promise<SiteDetail[]> {
  return (await request<{ sites: SiteDetail[] }>("/api/my/sites")).sites
}

export function getMySite(id: string): Promise<SiteDetail> {
  return request(`/api/my/sites/${encodeURIComponent(id)}`)
}

export function updateMySite(id: string, body: SiteRegistration): Promise<SiteDetail> {
  return request(`/api/my/sites/${encodeURIComponent(id)}`, { method: "PUT", ...json(body) })
}

export interface ConsentUpdate {
  train: boolean
  share_forecast_window: boolean
  public_forecasts: boolean
}

/** Pause or resume training, share the forecast window or not, public forecasts on or off. */
export function updateConsents(id: string, body: ConsentUpdate): Promise<SiteDetail> {
  return request(`/api/my/sites/${encodeURIComponent(id)}/consents`, { method: "PUT", ...json(body) })
}

/** Take the plant out of the federation for good (credentials revoked). */
export function leaveFederation(id: string, note: string): Promise<SiteDetail> {
  return request(`/api/my/sites/${encodeURIComponent(id)}/leave`, { method: "POST", ...json({ note }) })
}

export function decideSite(id: string, action: SiteAction, note?: string): Promise<SiteDetail> {
  return request(`/api/admin/sites/${encodeURIComponent(id)}/${action}`, { method: "POST", ...json(note ? { note } : {}) })
}

/** Admin: revoke the site's credentials so the operator can download a new kit. */
export function reissueKit(id: string, note: string): Promise<SiteDetail> {
  return request(`/api/admin/sites/${encodeURIComponent(id)}/reissue-kit`, { method: "POST", ...json({ note }) })
}

/**
 * Download the site kit. A POST (with the CSRF token): every download issues a new one-time
 * enrollment token and invalidates the previous unused one. Returns the zip and its file name.
 */
export async function downloadKit(id: string): Promise<{ blob: Blob; filename: string }> {
  const headers = new Headers()
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken)
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/my/sites/${encodeURIComponent(id)}/kit`, {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers,
    })
  } catch {
    throw new PlatformApiError(0, `Can't reach the API${API_BASE_URL ? ` at ${API_BASE_URL}` : ""}`)
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
  const disposition = response.headers.get("Content-Disposition") ?? ""
  const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? `fedwind-site-${id}.zip`
  return { blob: await response.blob(), filename }
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

// ---------------------------------------------------------------------------
// Telegram alerts (app/services/notifications.py)
// ---------------------------------------------------------------------------

export interface TelegramStatus {
  configured: boolean
  linked: boolean
  telegram_username: string | null
  linked_at: string | null
  bot_username: string | null
}

export function getTelegram(): Promise<TelegramStatus> {
  return request("/api/me/telegram")
}

export function linkTelegram(): Promise<{ url: string; expires_at: string }> {
  return request("/api/me/telegram/link", { method: "POST" })
}

export function unlinkTelegram(): Promise<{ linked: boolean }> {
  return request("/api/me/telegram", { method: "DELETE" })
}
