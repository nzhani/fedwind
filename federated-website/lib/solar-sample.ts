/**
 * Sample solar result for the "Preview Sample Results" button.
 *
 * Shows how a finished run will look on the /solar page once the backend
 * pipeline is implemented. The values are illustrative, not model output,
 * and use the same normalized scale the training pipeline reports.
 */

import type { SolarForecastPoint, SolarTarget, SolarTrainingResult } from "@/lib/solar-api"

// Rough peak irradiance (Wh/m²) per target, used only to shape the sample curve
const TARGET_PEAK: Record<SolarTarget, number> = {
  ALLSKY_SFC_SW_DWN: 850,
  ALLSKY_SFC_SW_DNI: 900,
  ALLSKY_SFC_SW_DIFF: 220,
}

// Cloudiness per day: clear, cloudy, mostly clear
const DAILY_CLOUD = [0.95, 0.55, 0.85]

// Seeded so the preview looks the same every time
function seeded(seed: number) {
  return () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296
    return seed / 4294967296
  }
}

const round4 = (n: number) => Math.round(n * 10000) / 10000

export function buildSampleSolarResult(opts: {
  target: SolarTarget
  predictionLength: number
  trainingModel: string
  dropoutRate: number
}): SolarTrainingResult {
  const rand = seeded(42)
  const peak = TARGET_PEAK[opts.target]
  const mean = peak * 0.25
  const std = peak * 0.33
  const startHour = opts.predictionLength === 1 ? 12 : 0

  const forecast: SolarForecastPoint[] = []
  const dayErrors: number[] = []
  let absSum = 0
  let sqSum = 0

  for (let step = 1; step <= opts.predictionLength; step++) {
    const hourOfRun = startHour + step - 1
    const hour = hourOfRun % 24
    const sun = Math.max(0, Math.sin((Math.PI * (hour - 6)) / 12)) ** 1.3
    const clear = peak * sun
    const actual = (clear * DAILY_CLOUD[Math.floor(hourOfRun / 24) % DAILY_CLOUD.length] - mean) / std
    const predicted = actual + (rand() - 0.5) * (sun > 0 ? 0.35 : 0.05)

    const err = predicted - actual
    absSum += Math.abs(err)
    sqSum += err * err
    if (sun > 0) dayErrors.push(Math.abs(err))

    forecast.push({
      step,
      timestamp: null,
      actual: round4(actual),
      predicted: round4(predicted),
      clear_sky: round4((clear - mean) / std),
    })
  }

  const n = forecast.length
  return {
    success: true,
    message: "Sample preview, not produced by a model",
    model_name: opts.trainingModel,
    target: opts.target,
    prediction_length: opts.predictionLength,
    dropout_rate: opts.dropoutRate,
    training_time_seconds: 0,
    metrics: {
      mae: round4(absSum / n),
      rmse: round4(Math.sqrt(sqSum / n)),
      daytime_mae: dayErrors.length ? round4(dayErrors.reduce((a, b) => a + b, 0) / dayErrors.length) : null,
      skill_score: null,
    },
    forecast,
    download_training_summary: null,
    download_timing_summary: null,
  }
}
