/**
 * API Service Layer
 *
 * Connects the Next.js frontend to the FastAPI backend.
 *
 * Flow for centralized training:
 *   1. uploadFile()    -> POST /api/upload      (save CSV, get saved filename)
 *   2. startTraining() -> POST /api/train       (run training, get results)
 *   3. listFiles()     -> GET  /api/files       (browse uploaded files)
 *   4. deleteFile()    -> DELETE /api/files/{fn} (remove a file)
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"
const TRAINING_API_URL = process.env.NEXT_PUBLIC_TRAINING_API_URL || API_BASE_URL


async function apiFetch<T>(endpoint: string, options: RequestInit = {}, useTrainingWorker = false): Promise<T> {
  const base = useTrainingWorker ? TRAINING_API_URL : API_BASE_URL
  const url = `${base}${endpoint}`
  const response = await fetch(url, { ...options })

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Unknown error" }))
    throw new Error(body.detail || `API Error: ${response.status}`)
  }
  return response.json()
}


export interface HealthResponse {
  status: string
  version: string
  environment: string
  timestamp: string
  services: Record<string, string>
}

export interface FileInfo {
  filename: string
  original_name: string
  size_bytes: number
  rows: number
  columns: number
  column_names: string[]
  preview: Record<string, unknown>[]
}

export interface UploadResponse {
  success: boolean
  message: string
  file: FileInfo
}

export interface TrainingConfig {
  training_model: string    // GPT4TS | LLAMA | BERT | BART
  prediction_length: number // 1, 72, 432
  dropout_rate: number      // 0.0 - 0.5
  mode: string              // centralized | federated
  // Centralized advanced params
  learning_rate?: number
  batch_size?: number
  seq_len?: number
  epochs?: number
  llm_layers?: number
  weight_decay?: number
  warmup_rounds?: number
  patch_size?: number
  patch_stride?: number
  hidden_size?: number
  kernel_size?: number
  // Federated-only fields
  federated_algorithm: string  // FedAvg | FedProx | FedBN | FedPer | SCAFFOLD
  num_clients: number          // 1 - 10
  num_rounds: number           // 1 - 50
  local_epochs: number         // 1 - 10
  proximal_mu?: number         // FedProx only
}

export interface TrainingMetrics {
  mae: number
  rmse: number
}

export interface ForecastPoint {
  step: number
  timestamp: string | null
  actual: number | null
  predicted: number
}

export interface TrainingResult {
  success: boolean
  message: string
  model_name: string
  prediction_length: number
  dropout_rate: number
  training_time_seconds: number
  metrics: TrainingMetrics
  forecast: ForecastPoint[]
  download_training_summary?: string | null
  download_timing_summary?: string | null
}

export interface FileListItem {
  filename: string
  size: number
  modified: string
}

export interface FileListResponse {
  files: FileListItem[]
  total: number
}

// Feedback types
export interface FeedbackEntry {
  id: string
  message: string
  name: string | null
  context: string | null
  created_at: string
}

export interface FeedbackResponse {
  success: boolean
  message: string
  entry: FeedbackEntry
}

export interface PublicAnswerItem {
  id: string
  question: string
  answer_text: string | null
  created_at: string
  answered_at: string | null
  asked_by: string
}

export interface PublicAnswersResponse {
  entries: PublicAnswerItem[]
  total: number
}

export interface ConversationMessageItem {
  id: string
  conversation_id: string
  sender_type: string
  sender_name: string | null
  message_text: string
  context: string | null
  created_at: string
  is_public: boolean
  telegram_message_id: number | null
  reply_to_message_id: string | null
}

export interface ConversationMessagesResponse {
  conversation_id: string
  entries: ConversationMessageItem[]
  total: number
}

// Kept for backward compatibility with federated mode UI
export interface ModelUpdateResponse {
  success?: boolean
  message: string
  update_id: string
  client_id?: string
  round_number: number
  received_at?: string
  queue_position: number
  total_clients_in_round?: number
}

export interface ModelSkeletonResponse {
  success?: boolean
  model_type: string
  version: string
  architecture: Record<string, unknown>
  hyperparameters: Record<string, unknown>
  instructions?: string
}

// ============================================================
// API Functions
// ============================================================

/** GET /health */
export async function checkHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health")
}

/** Test if backend is reachable */
export async function testConnection(): Promise<boolean> {
  try {
    await checkHealth()
    return true
  } catch {
    return false
  }
}

/**
 * POST /api/upload  -  Upload a single CSV file.
 * Returns the saved filename to use in the /api/train call.
 */
export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append("file", file)

  return apiFetch<UploadResponse>("/api/upload", {
    method: "POST",
    body: formData,
  }, true)
}

/**
 * POST /api/train  -  Start centralized training.
 * @param filename - The saved filename from uploadFile() response
 * @param config   - Training configuration from the dashboard form
 */
export interface ProgressUpdate {
  round: number
  total_rounds: number
  forecast: ForecastPoint[]
}

export async function startTraining(
  filename: string,
  config: TrainingConfig,
  onProgress?: (progress: ProgressUpdate) => void,
): Promise<TrainingResult> {
  // Submit job — returns immediately with job_id
  const { job_id } = await apiFetch<{ job_id: string; status: string }>("/api/train", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, config }),
  }, true)

  // Poll until done, updating chart with each round's predictions
  while (true) {
    await new Promise(r => setTimeout(r, 5000))

    // Poll progress for live chart update
    if (onProgress) {
      try {
        const progress = await apiFetch<ProgressUpdate>(`/api/job/${job_id}/progress`, {}, true)
        if (progress.forecast.length > 0) onProgress(progress)
      } catch { /* ignore progress errors */ }
    }

    // Poll job status
    const job = await apiFetch<{ status: string; result: TrainingResult | null; error: string | null }>(
      `/api/job/${job_id}`, {}, true
    )
    if (job.status === "done" && job.result) return job.result
    if (job.status === "failed") throw new Error(job.error || "Training failed")
  }
}

/** GET /api/files  -  List all uploaded CSV files */
export async function listUploadedFiles(): Promise<FileListResponse> {
  return apiFetch<FileListResponse>("/api/files", {}, true)
}

/** DELETE /api/files/{filename} */
export async function deleteUploadedFile(
  filename: string,
): Promise<{ success: boolean; message: string }> {
  return apiFetch(`/api/files/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  }, true)
}

// ---- Federated mode (kept for existing UI) ----

/** GET /model-update/skeleton */
export async function getModelSkeleton(): Promise<ModelSkeletonResponse> {
  return apiFetch<ModelSkeletonResponse>("/model-update/skeleton")
}

/** POST /model-update */
export async function submitModelUpdate(
  clientId: string,
  _modelVersion: string,
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
  return apiFetch<ModelUpdateResponse>("/model-update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: clientId,
      round_number: roundNumber,
      model_weights: weights,
      training_model: options?.trainingModel ?? "GPT4TS",
      federated_algorithm: options?.federatedAlgorithm ?? "FedAvg",
      prediction_length: options?.predictionLength ?? 6,
      dropout_rate: options?.dropoutRate ?? 0.2,
      num_clients: options?.numClients ?? 1,
      num_samples: options?.numSamples ?? 1000,
      training_loss: options?.trainingLoss ?? null,
    }),
  })
}

// ---- Feedback API ----

/** POST /api/feedback - Submit user feedback */
export async function submitFeedback(
  message: string,
  name?: string,
  context?: string,
): Promise<FeedbackResponse> {
  return apiFetch<FeedbackResponse>("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, name, context }),
  })
}

export async function getPublicAnswers(): Promise<PublicAnswersResponse> {
  return apiFetch<PublicAnswersResponse>("/api/feedback/public-answers")
}

export async function getFeedbackMessages(
  feedbackId: string,
): Promise<ConversationMessagesResponse> {
  return apiFetch<ConversationMessagesResponse>(`/api/feedback/${feedbackId}/messages`)
}

export async function createFeedbackFollowUp(
  feedbackId: string,
  message: string,
  name?: string,
  context?: string,
  replyToMessageId?: string,
): Promise<FeedbackResponse> {
  return apiFetch<FeedbackResponse>(`/api/feedback/${feedbackId}/follow-up`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      name,
      context,
      reply_to_message_id: replyToMessageId,
    }),
  })
}

export interface AggregateResponse {
  success: boolean
  message: string
  round_number: number
  num_clients_aggregated: number
  federated_algorithm: string
  training_model: string
  prediction_length: number
  mae: number
  rmse: number
  forecast: ForecastPoint[]
}

/** POST /model-update/aggregate — trigger server-side FedAvg aggregation for a round */
export async function aggregateFederatedRound(
  roundNumber: number,
  predictionLength: number,
): Promise<AggregateResponse> {
  return apiFetch<AggregateResponse>("/model-update/aggregate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ round_number: roundNumber, prediction_length: predictionLength }),
  })
}

// Legacy alias kept so existing imports don't break
export const uploadData = uploadFile
