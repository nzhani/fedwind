/**
 * Solar API Service Layer (skeleton)
 *
 * Mirrors lib/api.ts for the solar endpoints under /api/solar/*.
 *
 * Backend status: every endpoint except GET /api/solar/health returns
 * 501 Not Implemented until FastApi/app/services/solar_training_service.py
 * is implemented.
 *
 * Flow (identical to wind):
 *   1. uploadSolarFile()     -> POST /api/solar/upload
 *   2. startSolarTraining()  -> POST /api/solar/train, then polls
 *                               GET /api/solar/job/{id}[/progress]
 */

import type {
  ForecastPoint,
  TrainingConfig,
  TrainingMetrics,
  UploadResponse,
  FileListResponse,
  ModelSkeletonResponse,
  ModelUpdateResponse,
  AggregateResponse,
} from "@/lib/api"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"
const TRAINING_API_URL = process.env.NEXT_PUBLIC_TRAINING_API_URL || API_BASE_URL

async function solarFetch<T>(endpoint: string, options: RequestInit = {}, useTrainingWorker = false): Promise<T> {
  const base = useTrainingWorker ? TRAINING_API_URL : API_BASE_URL
  const url = `${base}/api/solar${endpoint}`
  const response = await fetch(url, { ...options })

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Unknown error" }))
    throw new Error(body.detail || `API Error: ${response.status}`)
  }
  return response.json()
}


// ============================================================
// Types
// ============================================================

/** NASA POWER hourly irradiance parameters */
export type SolarTarget = "ALLSKY_SFC_SW_DWN" | "ALLSKY_SFC_SW_DNI" | "ALLSKY_SFC_SW_DIFF"

export interface SolarTrainingConfig extends TrainingConfig {
  target: SolarTarget
  mask_night: boolean      // exclude night hours from loss/metrics
  use_clear_sky: boolean   // use CLRSKY_SFC_SW_DWN as an input feature
}

export interface SolarTrainingMetrics extends TrainingMetrics {
  daytime_mae?: number | null
  skill_score?: number | null  // 1 - RMSE_model / RMSE_persistence
}

export interface SolarForecastPoint extends ForecastPoint {
  clear_sky?: number | null
}

export interface SolarTrainingResult {
  success: boolean
  message: string
  model_name: string
  target: SolarTarget
  prediction_length: number
  dropout_rate: number
  training_time_seconds: number
  metrics: SolarTrainingMetrics
  forecast: SolarForecastPoint[]
  download_training_summary?: string | null
  download_timing_summary?: string | null
}

export interface SolarProgressUpdate {
  round: number
  total_rounds: number
  forecast: SolarForecastPoint[]
}

export interface SolarHealthResponse {
  status: string           // "skeleton" | "ok"
  implemented: boolean
  module: string
  targets: SolarTarget[]
  prediction_lengths: number[]
  endpoints: string[]
}



// ============================================================
// Constants shared by the dashboard and the mock
// ============================================================

export const SOLAR_TARGETS: { value: SolarTarget; short: string; label: string }[] = [
  { value: "ALLSKY_SFC_SW_DWN", short: "GHI", label: "GHI - Global Horizontal Irradiance" },
  { value: "ALLSKY_SFC_SW_DNI", short: "DNI", label: "DNI - Direct Normal Irradiance" },
  { value: "ALLSKY_SFC_SW_DIFF", short: "DHI", label: "DHI - Diffuse Horizontal Irradiance" },
]

export const SOLAR_PREDICTION_LENGTHS = [
  { value: "1", label: "1 (next hour)" },
  { value: "24", label: "24 (day-ahead)" },
  { value: "72", label: "72 (3 days ahead)" },
]



// ============================================================
// API Functions
// ============================================================

/** GET /api/solar/health */
export async function getSolarHealth(): Promise<SolarHealthResponse> {
  return solarFetch<SolarHealthResponse>("/health")
}

/** POST /api/solar/upload */
export async function uploadSolarFile(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append("file", file)

  return solarFetch<UploadResponse>("/upload", {
    method: "POST",
    body: formData,
  }, true)
}

/** GET /api/solar/files */
export async function listSolarFiles(): Promise<FileListResponse> {
  return solarFetch<FileListResponse>("/files", {}, true)
}

/** DELETE /api/solar/files/{filename} */
export async function deleteSolarFile(
  filename: string,
): Promise<{ success: boolean; message: string }> {
  return solarFetch(`/files/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  }, true)
}

/**
 * POST /api/solar/train, then poll GET /api/solar/job/{job_id} until done.
 * Same contract as startTraining() in lib/api.ts.
 */
export async function startSolarTraining(
  filename: string,
  config: SolarTrainingConfig,
  onProgress?: (progress: SolarProgressUpdate) => void,
): Promise<SolarTrainingResult> {
  const { job_id } = await solarFetch<{ job_id: string; status: string }>("/train", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, config }),
  }, true)

  while (true) {
    await new Promise(r => setTimeout(r, 5000))

    if (onProgress) {
      try {
        const progress = await solarFetch<SolarProgressUpdate>(`/job/${job_id}/progress`, {}, true)
        if (progress.forecast.length > 0) onProgress(progress)
      } catch { /* ignore progress errors */ }
    }

    const job = await solarFetch<{ status: string; result: SolarTrainingResult | null; error: string | null }>(
      `/job/${job_id}`, {}, true
    )
    if (job.status === "done" && job.result) return job.result
    if (job.status === "failed") throw new Error(job.error || "Solar training failed")
  }
}

// ---- Federated client flow ----

/** GET /api/solar/model-update/skeleton */
export async function getSolarModelSkeleton(): Promise<ModelSkeletonResponse> {
  return solarFetch<ModelSkeletonResponse>("/model-update/skeleton")
}

/** POST /api/solar/model-update */
export async function submitSolarModelUpdate(
  clientId: string,
  weights: Record<string, unknown>,
  roundNumber: number,
  options?: {
    trainingModel?: string
    federatedAlgorithm?: string
    predictionLength?: number
    dropoutRate?: number
    numClients?: number
    numSamples?: number
    trainingLoss?: number
  },
): Promise<ModelUpdateResponse> {
  return solarFetch<ModelUpdateResponse>("/model-update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: clientId,
      round_number: roundNumber,
      model_weights: weights,
      training_model: options?.trainingModel ?? "GPT4TS",
      federated_algorithm: options?.federatedAlgorithm ?? "FedAvg",
      prediction_length: options?.predictionLength ?? 24,
      dropout_rate: options?.dropoutRate ?? 0.2,
      num_clients: options?.numClients ?? 1,
      num_samples: options?.numSamples ?? 1000,
      training_loss: options?.trainingLoss ?? null,
    }),
  })
}

/** POST /api/solar/model-update/aggregate */
export async function aggregateSolarRound(
  roundNumber: number,
  predictionLength: number,
): Promise<AggregateResponse> {
  return solarFetch<AggregateResponse>("/model-update/aggregate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ round_number: roundNumber, prediction_length: predictionLength }),
  })
}
