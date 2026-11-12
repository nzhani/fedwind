"use client"

import React from "react"

import { useState, useEffect, useRef } from "react"
import { PageLayout, StaggerContainer, StaggerItem } from "@/components/page-layout"
import {
  uploadSolarFile,
  startSolarTraining,
  SOLAR_TARGETS,
  SOLAR_PREDICTION_LENGTHS,
  type SolarForecastPoint,
  type SolarProgressUpdate,
  type SolarTarget,
  type SolarTrainingConfig,
  type SolarTrainingResult,
} from "@/lib/solar-api"
import { buildSampleSolarResult } from "@/lib/solar-sample"
import { SectionHeader } from "@/components/section-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Upload,
  Play,
  Sun,
  Clock,
  FileText,
  AlertCircle,
  CheckCircle2,
  BarChart3,
  Shield,
  Server,
  Trash2,
  Download,
  Eye,
  Info,
} from "lucide-react"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
} from "recharts"

const TRAINING_API_URL = process.env.NEXT_PUBLIC_TRAINING_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"

export default function SolarDashboardPage() {
  // Form state
  const [files, setFiles] = useState<File[]>([])
  const [target, setTarget] = useState<SolarTarget>("ALLSKY_SFC_SW_DWN")
  const [trainingModel, setTrainingModel] = useState("GPT4TS_LINEAR")
  const [predictionLength, setPredictionLength] = useState("24")
  const [mode, setMode] = useState("federated")
  const [federatedAlgorithm, setFederatedAlgorithm] = useState("FedAvg")
  const [numClients, setNumClients] = useState("5")
  const [numRounds, setNumRounds] = useState("10")
  const [localEpochs, setLocalEpochs] = useState("2")
  const [epochs, setEpochs] = useState("10")
  const [learningRate, setLearningRate] = useState("0.0001")
  const [maskNight, setMaskNight] = useState(true)
  const [useClearSky, setUseClearSky] = useState(true)

  // Advanced params
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [batchSize, setBatchSize] = useState("64")
  const [dropoutRate, setDropoutRate] = useState("0.2")
  const [seqLen, setSeqLen] = useState("168")
  const [llmLayers, setLlmLayers] = useState("2")

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false)
  const [processingStep, setProcessingStep] = useState("")
  const [showResults, setShowResults] = useState(false)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (isProcessing) {
      setElapsedSeconds(0)
      timerRef.current = setInterval(() => setElapsedSeconds(s => s + 1), 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [isProcessing])

  // API state
  const [trainingResult, setTrainingResult] = useState<SolarTrainingResult | null>(null)
  const [liveForecast, setLiveForecast] = useState<SolarForecastPoint[]>([])
  const [liveRound, setLiveRound] = useState<{ current: number; total: number } | null>(null)
  const [isPreview, setIsPreview] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const targetShort = SOLAR_TARGETS.find(t => t.value === target)?.short ?? "GHI"

  // File upload handler
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files)
      setFiles(prev => [...prev, ...newFiles])
      setError(null)
    }
  }

  // Remove a file from the selection
  const handleRemoveFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }

  // Sample results: shows how a finished run will look until the solar backend is implemented
  const handlePreviewResults = () => {
    setError(null)
    setLiveForecast([])
    setLiveRound(null)
    setTrainingResult(buildSampleSolarResult({
      target,
      predictionLength: parseInt(predictionLength),
      trainingModel,
      dropoutRate: parseFloat(dropoutRate),
    }))
    setIsPreview(true)
    setShowResults(true)
  }

  // Upload files -> train on the last one (same flow as the wind dashboard)
  const handleStartTraining = async () => {
    setIsProcessing(true)
    setIsPreview(false)
    setError(null)
    setTrainingResult(null)
    setLiveForecast([])
    setLiveRound(null)

    try {
      if (files.length === 0) {
        setError("Please select at least one CSV file to upload")
        return
      }

      // Step 1: Upload all files, keep track of saved filenames
      const savedFilenames: string[] = []
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        setProcessingStep(`Uploading file ${i + 1} of ${files.length}: ${file.name}...`)
        const uploadResult = await uploadSolarFile(file)
        savedFilenames.push(uploadResult.file.filename)
      }

      // Step 2: Train on the last uploaded file with config from the form
      const trainFilename = savedFilenames[savedFilenames.length - 1]
      setProcessingStep(
        mode === "federated"
          ? `Running federated simulation: ${trainingModel.replace("_LINEAR", "")} / ${federatedAlgorithm} / ${numClients} clients...`
          : `Training ${trainingModel.replace("_LINEAR", "")} model on ${targetShort} (${predictionLength}-step horizon)...`
      )

      const config: SolarTrainingConfig = {
        target,
        mask_night: maskNight,
        use_clear_sky: useClearSky,
        training_model: trainingModel,
        prediction_length: parseInt(predictionLength),
        dropout_rate: parseFloat(dropoutRate),
        mode,
        federated_algorithm: federatedAlgorithm,
        num_clients: parseInt(numClients),
        num_rounds: parseInt(numRounds),
        local_epochs: parseInt(localEpochs),
        llm_layers: parseInt(llmLayers),
        learning_rate: parseFloat(learningRate),
        batch_size: parseInt(batchSize),
        seq_len: parseInt(seqLen),
        epochs: parseInt(epochs),
      }

      const onProgress = (p: SolarProgressUpdate) => {
        setLiveForecast(p.forecast)
        setLiveRound({ current: p.round, total: p.total_rounds })
        setShowResults(true)
      }
      const result = await startSolarTraining(trainFilename, config, onProgress)
      setTrainingResult(result)
      setLiveForecast([])
      setShowResults(true)

      // Reset file selection
      setFiles([])
      const fileInput = document.getElementById("solar-file-upload") as HTMLInputElement
      if (fileInput) fileInput.value = ""
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred")
    } finally {
      setIsProcessing(false)
      setProcessingStep("")
    }
  }

  const chartSource = trainingResult && !isProcessing ? trainingResult.forecast : liveForecast

  return (
    <PageLayout>
      {/* Header */}
      <section className="bg-gradient-to-b from-primary/5 to-background">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <SectionHeader
              badge="Solar Forecasting"
              title="Solar Irradiance Forecasting Dashboard"
              description="Upload your solar irradiance data, configure training parameters, and view forecasting results. Choose between centralized or privacy-preserving federated learning."
              centered
            />
          </div>
        </div>
      </section>

      {/* Error Display */}
      {error && (
        <section className="mx-auto max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-red-800">Error</h4>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        </section>
      )}

      {/* Training Success banner */}
      {trainingResult && !isPreview && (
        <section className="mx-auto max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
          <div className="rounded-lg border border-green-200 bg-green-50 p-4 flex items-start gap-3">
            <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-green-800">Training Complete</h4>
              <p className="text-sm text-green-700">
                {trainingResult.message} | MAE: {trainingResult.metrics.mae} |{" "}
                RMSE: {trainingResult.metrics.rmse} |{" "}
                Time: {trainingResult.training_time_seconds}s
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Training Progress (shown during processing) */}
      {isProcessing && (
        <section className="mx-auto max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
          <Card className="border-primary/20 bg-primary/5">
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                <div className="flex-1">
                  <h4 className="font-semibold text-foreground">
                    {mode === "federated" ? "Federated Training in Progress..." : "Centralized Training in Progress..."}
                  </h4>
                  <p className="text-sm text-muted-foreground">{processingStep}</p>
                </div>
                <div className="flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-primary">
                  <Clock className="h-4 w-4" />
                  <span className="font-mono text-sm font-semibold tabular-nums">
                    {String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:{String(elapsedSeconds % 60).padStart(2, "0")}
                  </span>
                </div>
              </div>
              <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full w-2/3 animate-pulse rounded-full bg-primary" />
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                {mode === "federated"
                  ? "Your data stays on your device. Only model updates are shared with the server."
                  : "Your data is being processed on the server for model training."}
              </p>
            </CardContent>
          </Card>
        </section>
      )}

      {/* Main Dashboard */}
      <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <StaggerContainer className="grid gap-6 xl:grid-cols-3">
          {/* Controls Panel */}
          <StaggerItem className="xl:col-span-1">
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-primary" />
                  Configuration
                </CardTitle>
                <CardDescription>Set up your training parameters</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* File Upload */}
                <div className="space-y-2">
                  <Label htmlFor="solar-file-upload">Upload CSV Data</Label>
                  <div className="relative">
                    <input
                      id="solar-file-upload"
                      type="file"
                      accept=".csv"
                      multiple
                      onChange={handleFileChange}
                      className="hidden"
                    />
                    <label
                      htmlFor="solar-file-upload"
                      className="flex h-32 w-full cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-muted/30 transition-colors hover:border-primary hover:bg-muted/50"
                    >
                      <Upload className="h-8 w-8 text-muted-foreground mb-2" />
                      <span className="text-sm text-muted-foreground">
                        Click to upload CSV
                      </span>
                      <span className="text-xs text-muted-foreground mt-1">or drag and drop</span>
                    </label>
                  </div>

                  {/* File Preview Cards - Shows all selected files */}
                  {files.length > 0 && (
                    <div className="space-y-2">
                      {files.map((file, index) => (
                        <div
                          key={`${file.name}-${index}`}
                          className="rounded-lg border border-accent bg-accent/5 p-4 space-y-2 animate-in fade-in slide-in-from-top-2"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-3 flex-1 min-w-0">
                              <CheckCircle2 className="h-5 w-5 text-accent shrink-0 mt-0.5" />
                              <div className="flex-1 min-w-0">
                                <p className="font-semibold text-foreground text-sm truncate">{file.name}</p>
                                <p className="text-xs text-muted-foreground mt-1">
                                  {(file.size / 1024).toFixed(2)} KB
                                </p>
                              </div>
                            </div>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleRemoveFile(index)}
                              className="text-destructive hover:text-destructive hover:bg-destructive/10 shrink-0"
                            >
                              <Trash2 className="h-4 w-4" />
                              <span className="sr-only">Delete file</span>
                            </Button>
                          </div>
                        </div>
                      ))}
                      <p className="text-xs text-accent/80">
                        {files.length} file{files.length > 1 ? "s" : ""} ready to upload. Click "Start Forecasting" below to begin.
                      </p>
                    </div>
                  )}
                </div>

                {/* Training Model Selection */}
                <div className="space-y-2">
                  <Label htmlFor="solar-model">Training Model</Label>
                  <Select value={trainingModel} onValueChange={setTrainingModel}>
                    <SelectTrigger id="solar-model">
                      <SelectValue placeholder="Select model" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="GPT4TS_LINEAR">GPT4TS</SelectItem>
                      <SelectItem value="LLAMA_LINEAR">LLaMA</SelectItem>
                      <SelectItem value="BERT_LINEAR">BERT</SelectItem>
                      <SelectItem value="BART_LINEAR">BART</SelectItem>
                      <SelectItem value="OPT_LINEAR">OPT</SelectItem>
                      <SelectItem value="GEMMA_LINEAR">Gemma</SelectItem>
                      <SelectItem value="QWEN_LINEAR">Qwen</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">Selected: {trainingModel.replace("_LINEAR", "")}</p>
                </div>

                {/* Forecast Target */}
                <div className="space-y-2">
                  <Label htmlFor="solar-target">Forecast Target</Label>
                  <Select value={target} onValueChange={(v) => setTarget(v as SolarTarget)}>
                    <SelectTrigger id="solar-target">
                      <SelectValue placeholder="Select target" />
                    </SelectTrigger>
                    <SelectContent>
                      {SOLAR_TARGETS.map(t => (
                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">CSV column: {target}</p>
                </div>

                {/* Prediction Length */}
                <div className="space-y-2">
                  <Label htmlFor="solar-prediction-length">Prediction Length (Steps)</Label>
                  <Select value={predictionLength} onValueChange={setPredictionLength}>
                    <SelectTrigger id="solar-prediction-length">
                      <SelectValue placeholder="Select prediction length" />
                    </SelectTrigger>
                    <SelectContent>
                      {SOLAR_PREDICTION_LENGTHS.map(p => (
                        <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">Forecast {predictionLength} hour{predictionLength !== "1" ? "s" : ""} ahead</p>
                </div>

                {/* Training Mode */}
                <div className="space-y-2">
                  <Label htmlFor="solar-mode">Training Mode</Label>
                  <Select value={mode} onValueChange={setMode}>
                    <SelectTrigger id="solar-mode">
                      <SelectValue placeholder="Select mode" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="federated">
                        <div className="flex items-center gap-2">
                          <Shield className="h-4 w-4" />
                          Federated (Privacy-Preserving)
                        </div>
                      </SelectItem>
                      <SelectItem value="centralized">
                        <div className="flex items-center gap-2">
                          <Server className="h-4 w-4" />
                          Centralized (Server Upload)
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <div
                    className={`text-xs p-2 rounded ${mode === "federated" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"}`}
                  >
                    {mode === "federated"
                      ? "Data stays on your device. Only model updates are shared."
                      : "Data is uploaded to server for training."}
                  </div>
                </div>

                {/* Federated Algorithm + Clients - Only for Federated Mode */}
                {mode === "federated" && (
                  <div className="space-y-6 pt-2 border-t border-border">
                    <div className="space-y-2">
                      <Label htmlFor="solar-algorithm">Federated Learning Algorithm</Label>
                      <Select value={federatedAlgorithm} onValueChange={setFederatedAlgorithm}>
                        <SelectTrigger id="solar-algorithm">
                          <SelectValue placeholder="Select algorithm" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="FedAvg">FedAvg - Federated Averaging</SelectItem>
                          <SelectItem value="FedProx">FedProx - Proximal Term</SelectItem>
                          <SelectItem value="SCAFFOLD">SCAFFOLD - Control Variates</SelectItem>
                          <SelectItem value="StatAvg">StatAvg - Statistics Averaging</SelectItem>
                          <SelectItem value="FedPer">FedPer - Personalized Head</SelectItem>
                          <SelectItem value="FedLN">FedLN - Local Layer Norms</SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">Selected: {federatedAlgorithm}</p>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="solar-clients">Number of Clients</Label>
                      <div className="flex gap-2 items-center">
                        <input id="solar-clients" type="number" min="1" max="10" value={numClients}
                          onChange={(e) => { const v = parseInt(e.target.value); if (v >= 1 && v <= 10) setNumClients(e.target.value) }}
                          className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm" placeholder="5" />
                        <span className="text-sm text-muted-foreground font-mono">/ 10</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Learning Rate - basic */}
                <div className="space-y-2">
                  <Label htmlFor="solar-lr">Learning Rate</Label>
                  <input
                    id="solar-lr"
                    type="text"
                    inputMode="decimal"
                    value={learningRate}
                    onChange={(e) => setLearningRate(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>

                {/* Advanced toggle */}
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={() => setShowAdvanced((v) => !v)}
                    className="text-xs font-medium text-primary underline underline-offset-2 hover:no-underline"
                  >
                    {showAdvanced ? "▲ Hide Advanced Parameters" : "▼ Show Advanced Parameters"}
                  </button>
                </div>

                {/* Advanced params */}
                {showAdvanced && (
                  <div className="space-y-4 rounded-lg border border-border bg-muted/20 p-4">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Advanced Parameters
                    </p>

                    {mode === "federated" ? (
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label htmlFor="solar-rounds" className="text-xs">Communication Rounds</Label>
                          <input id="solar-rounds" type="number" min="1" max="50" value={numRounds}
                            onChange={(e) => setNumRounds(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="solar-local-epochs" className="text-xs">Local Epochs per Round</Label>
                          <input id="solar-local-epochs" type="number" min="1" max="10" value={localEpochs}
                            onChange={(e) => setLocalEpochs(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <Label htmlFor="solar-epochs" className="text-xs">Epochs (Rounds)</Label>
                        <input id="solar-epochs" type="number" min="1" max="50" value={epochs}
                          onChange={(e) => setEpochs(e.target.value)}
                          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-2">
                      <div className="space-y-1">
                        <Label htmlFor="solar-batch" className="text-xs">Batch Size</Label>
                        <input id="solar-batch" type="number" min="1" value={batchSize}
                          onChange={(e) => setBatchSize(e.target.value)}
                          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="solar-dropout" className="text-xs">Dropout Rate</Label>
                        <input id="solar-dropout" type="number" min="0" max="0.5" step="0.05" value={dropoutRate}
                          onChange={(e) => setDropoutRate(e.target.value)}
                          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="solar-seq-len" className="text-xs">Sequence Length</Label>
                        <input id="solar-seq-len" type="number" min="24" value={seqLen}
                          onChange={(e) => setSeqLen(e.target.value)}
                          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="solar-llm-layers" className="text-xs">LLM Layers</Label>
                        <input id="solar-llm-layers" type="number" min="1" max="12" value={llmLayers}
                          onChange={(e) => setLlmLayers(e.target.value)}
                          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <Label htmlFor="mask-night" className="text-xs">Mask Night Hours</Label>
                        <p className="text-xs text-muted-foreground">Exclude zero-irradiance hours from loss and metrics</p>
                      </div>
                      <Switch id="mask-night" checked={maskNight} onCheckedChange={setMaskNight} />
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <Label htmlFor="clear-sky" className="text-xs">Clear-Sky Feature</Label>
                        <p className="text-xs text-muted-foreground">Use CLRSKY_SFC_SW_DWN as an input if present</p>
                      </div>
                      <Switch id="clear-sky" checked={useClearSky} onCheckedChange={setUseClearSky} />
                    </div>
                  </div>
                )}

                {/* Start Button */}
                <Button
                  className="w-full gap-2"
                  onClick={handleStartTraining}
                  disabled={isProcessing || files.length === 0}
                >
                  {isProcessing ? (
                    <>
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4" />
                      Start Forecasting
                    </>
                  )}
                </Button>

                {/* Sample results preview */}
                <Button
                  variant="outline"
                  className="w-full gap-2 bg-transparent"
                  onClick={handlePreviewResults}
                  disabled={isProcessing}
                >
                  <Eye className="h-4 w-4" />
                  Preview Sample Results
                </Button>
              </CardContent>
            </Card>
          </StaggerItem>

          {/* Results Panel */}
          <StaggerItem className="xl:col-span-2">
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-primary" />
                  Solar Irradiance Forecasting Results
                </CardTitle>
                <CardDescription>
                  {showResults && trainingResult
                    ? `${trainingResult.prediction_length}-step ${targetShort} forecast using ${trainingResult.model_name} (${mode === "federated" ? "Federated" : "Centralized"})${isPreview ? " · sample preview" : ""}`
                    : showResults
                      ? `${predictionLength}-step forecast ${mode === "federated" ? "(Federated Model)" : "(Centralized Model)"}`
                      : "Configure and run to see predictions"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {showResults ? (
                  <div className="space-y-6">
                    {/* Stats Row - Only MAE + RMSE + Time */}
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div className="rounded-lg border border-border bg-muted/30 p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm">
                          <Sun className="h-4 w-4" />
                          MAE
                        </div>
                        <div className="mt-1 text-2xl font-bold text-foreground">
                          {trainingResult ? trainingResult.metrics.mae : "--"}
                        </div>
                        <div className="text-xs text-muted-foreground">Mean Absolute Error (normalized)</div>
                      </div>
                      <div className="rounded-lg border border-border bg-muted/30 p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm">
                          <BarChart3 className="h-4 w-4" />
                          RMSE
                        </div>
                        <div className="mt-1 text-2xl font-bold text-foreground">
                          {trainingResult ? trainingResult.metrics.rmse : "--"}
                        </div>
                        <div className="text-xs text-muted-foreground">Root Mean Square Error (normalized)</div>
                      </div>
                      <div className="rounded-lg border border-border bg-muted/30 p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm">
                          <Clock className="h-4 w-4" />
                          Time
                        </div>
                        <div className="mt-1 text-2xl font-bold text-foreground">
                          {trainingResult && !isPreview ? `${trainingResult.training_time_seconds}s` : "--s"}
                        </div>
                        <div className="text-xs text-muted-foreground">Training Duration</div>
                      </div>
                    </div>

                    {/* Federated Mode Info Panel */}
                    {mode === "federated" && trainingResult && (
                      <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                        <h4 className="font-semibold text-green-800 flex items-center gap-2 mb-3">
                          <Shield className="h-4 w-4 text-green-600" />
                          Federated Learning - Privacy Preserved
                        </h4>
                        <div className="grid gap-3 sm:grid-cols-3">
                          <div>
                            <div className="text-xs text-muted-foreground">Algorithm</div>
                            <div className="text-lg font-semibold text-foreground">
                              {federatedAlgorithm}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground">Clients</div>
                            <div className="text-lg font-semibold text-foreground">
                              {numClients}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground">Model</div>
                            <div className="text-lg font-semibold text-foreground">
                              {trainingResult.model_name}
                            </div>
                          </div>
                        </div>
                        <p className="text-xs text-green-600 mt-3">
                          Data stayed on each client device. Only model updates were aggregated on the server.
                        </p>
                      </div>
                    )}

                    {/* Irradiance Chart */}
                    <div>
                      <h4 className="font-semibold text-foreground mb-3 flex items-center gap-2">
                        <Sun className="h-4 w-4 text-primary" />
                        {targetShort} Forecast
                        <span className="text-xs font-normal text-muted-foreground ml-1">
                          {liveRound && isProcessing
                            ? `— Round ${liveRound.current}/${liveRound.total} (live)`
                            : trainingResult ? `— ${trainingResult.forecast.length} steps (normalized scale)` : ""}
                        </span>
                      </h4>

                      <div style={{ width: "100%", height: 280 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart
                            data={chartSource.map((p) => ({
                              label: `S${p.step}`,
                              predicted: p.predicted,
                              ...(p.actual !== null && p.actual !== undefined ? { actual: p.actual } : {}),
                            }))}
                            margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                            <XAxis
                              dataKey="label"
                              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                              interval="preserveStartEnd"
                            />
                            <YAxis
                              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                              label={{
                                value: "normalized",
                                angle: -90,
                                position: "insideLeft",
                                fontSize: 12,
                                fill: "hsl(var(--muted-foreground))",
                              }}
                              domain={["auto", "auto"]}
                            />
                            <Tooltip
                              contentStyle={{
                                backgroundColor: "hsl(var(--background))",
                                border: "1px solid hsl(var(--border))",
                                borderRadius: "6px",
                                fontSize: "12px",
                                color: "hsl(var(--foreground))",
                              }}
                              formatter={(value: number, name: string) => [Number(value).toFixed(4), name]}
                              labelFormatter={(label) => `${label}`}
                            />
                            <Legend wrapperStyle={{ fontSize: "12px" }} />
                            {chartSource.some((p) => p.actual !== null && p.actual !== undefined) && (
                              <Line
                                type="monotone"
                                dataKey="actual"
                                stroke="#A23B72"
                                strokeWidth={2}
                                dot={chartSource.length === 1}
                                name="Actual"
                                connectNulls={false}
                                isAnimationActive={false}
                              />
                            )}
                            <Line
                              type="monotone"
                              dataKey="predicted"
                              stroke="#2E86AB"
                              strokeWidth={2}
                              strokeDasharray="5 5"
                              dot={chartSource.length === 1}
                              name="Predicted"
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* Download Results */}
                    {trainingResult && (
                      trainingResult.download_training_summary ||
                      trainingResult.download_timing_summary
                    ) && (
                      <div className="rounded-lg border border-border bg-muted/20 p-4">
                        <h4 className="font-semibold text-foreground text-sm mb-3 flex items-center gap-2">
                          <FileText className="h-4 w-4 text-primary" />
                          Download Training Results
                        </h4>
                        <div className="flex flex-wrap gap-3">
                          {trainingResult.download_training_summary && (
                            <a
                              href={`${TRAINING_API_URL}${trainingResult.download_training_summary}`}
                              download="training_summary.csv"
                              className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-muted/50 transition-colors"
                            >
                              <Download className="h-4 w-4 text-primary" />
                              training_summary.csv
                            </a>
                          )}
                          {trainingResult.download_timing_summary && (
                            <a
                              href={`${TRAINING_API_URL}${trainingResult.download_timing_summary}`}
                              download="timing_summary.csv"
                              className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-muted/50 transition-colors"
                            >
                              <Download className="h-4 w-4 text-primary" />
                              timing_summary.csv
                            </a>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                          Per-round metrics and wall-clock timing from this training run.
                        </p>
                      </div>
                    )}

                    {/* Training Info (if complete) */}
                    {trainingResult && (
                      <div className="rounded-lg border border-border bg-muted/20 p-4">
                        <h4 className="font-semibold text-foreground text-sm mb-2">Training Summary</h4>
                        <div className="grid gap-2 sm:grid-cols-4 text-sm">
                          <div>
                            <span className="text-muted-foreground">Model:</span>{" "}
                            <span className="text-foreground">{trainingResult.model_name}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Target:</span>{" "}
                            <span className="text-foreground">{targetShort}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Horizon:</span>{" "}
                            <span className="text-foreground">{trainingResult.prediction_length} steps</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Time:</span>{" "}
                            <span className="text-foreground">{isPreview ? "--" : `${trainingResult.training_time_seconds}s`}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex h-[400px] flex-col items-center justify-center text-center">
                    <Clock className="h-12 w-12 text-muted-foreground mb-4" />
                    <h4 className="font-semibold text-foreground">No Results Yet</h4>
                    <p className="text-sm text-muted-foreground mt-1 max-w-xs">
                      Upload your data and click &quot;Start Forecasting&quot; to see solar irradiance predictions.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </StaggerItem>
        </StaggerContainer>
      </section>
    </PageLayout>
  )
}
