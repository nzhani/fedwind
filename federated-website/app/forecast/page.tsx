"use client"

// Forecast viewer (plan T1.9, T3.6; FR-22, FR-23, FR-26):
// energy type -> site -> horizon, then forecast vs actual on one chart.
// The forecast comes from the site's own inference service via /api/forecast.

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { Sun, Wind, MapPin, Clock, Play, Zap, Gauge } from "lucide-react"
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { PageLayout } from "@/components/page-layout"
import { ApiErrorNotice, PageHeader, formatTimestamp } from "@/components/platform"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/utils"
import {
  HORIZONS,
  HORIZON_LABELS,
  getForecast,
  getSites,
  listModels,
  type ForecastResponse,
  type Horizon,
  type RegisteredModel,
  type Site,
} from "@/lib/platform-api"

type ChartRow = { t: number; actual?: number; forecast?: number }

function StepTitle({ n, title, icon: Icon }: { n: number; title: string; icon: typeof Wind }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
        {n}
      </span>
      <Icon className="h-4 w-4 text-primary" />
      <span className="font-medium text-foreground">{title}</span>
    </div>
  )
}

export default function ForecastPage() {
  const [sites, setSites] = useState<Site[]>([])
  const [models, setModels] = useState<RegisteredModel[]>([])
  const [site, setSite] = useState<string>("")
  const [horizon, setHorizon] = useState<Horizon>(72)
  const [asOf, setAsOf] = useState("") // datetime-local value, treated as UTC
  const [view, setView] = useState<"speed" | "power">("speed")
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ForecastResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loadError, setLoadError] = useState<unknown>(null)

  useEffect(() => {
    getSites("wind")
      .then((s) => {
        const active = s.filter((x) => x.status === "active")
        setSites(active)
        if (active.length) setSite((cur) => cur || active[0].id)
      })
      .catch(setLoadError)
    listModels().then(setModels).catch(() => setModels([]))
  }, [])

  const model = models.find((m) => m.energy_type === "wind" && m.horizon === horizon)
  const siteName = sites.find((s) => s.id === site)?.name ?? site

  const handleForecast = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await getForecast({
        energyType: "wind",
        site,
        horizon,
        asOf: asOf ? `${asOf}:00Z` : undefined,
      })
      setResult(res)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  const hasPower = !!result?.forecast.some((p) => p.wind_power_kw != null)

  const chartData = useMemo<ChartRow[]>(() => {
    if (!result) return []
    const rows = new Map<number, ChartRow>()
    const pick = (p: { wind_speed: number; wind_power_kw?: number | null }) =>
      view === "power" ? (p.wind_power_kw ?? undefined) : p.wind_speed
    for (const p of result.actual) {
      const t = Date.parse(p.timestamp)
      rows.set(t, { ...rows.get(t), t, actual: pick(p) })
    }
    for (const p of result.forecast) {
      const t = Date.parse(p.timestamp)
      rows.set(t, { ...rows.get(t), t, forecast: pick(p) })
    }
    return [...rows.values()].sort((a, b) => a.t - b.t)
  }, [result, view])

  const errorStats = useMemo(() => {
    if (!result) return null
    const actualAt = new Map(result.actual.map((p) => [Date.parse(p.timestamp), p.wind_speed]))
    const pairs = result.forecast
      .map((p) => [p.wind_speed, actualAt.get(Date.parse(p.timestamp))] as const)
      .filter((x): x is readonly [number, number] => x[1] !== undefined)
    if (!pairs.length) return null
    const mae = pairs.reduce((s, [f, a]) => s + Math.abs(f - a), 0) / pairs.length
    const rmse = Math.sqrt(pairs.reduce((s, [f, a]) => s + (f - a) ** 2, 0) / pairs.length)
    return { mae, rmse, n: pairs.length }
  }, [result])

  const unit = view === "power" ? "kW" : (result?.unit ?? "m/s")
  const asOfMs = result ? Date.parse(result.as_of) : undefined
  // Everything on this page is in UTC, like the issue-time input and the data (DR-09).
  const tickFormat = (t: number) =>
    new Date(t).toLocaleString(undefined, {
      timeZone: "UTC",
      month: "short",
      day: "numeric",
      ...(horizon > 72 ? {} : { hour: "2-digit" }),
    })
  const formatUtc = (iso: string) =>
    `${new Date(iso).toLocaleString(undefined, { timeZone: "UTC", year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} UTC`

  return (
    <PageLayout>
      <PageHeader
        badge="Forecast"
        title="Wind Forecast by Site"
        description="Choose an energy type, a site and a horizon. The forecast comes from the current global federated model, computed next to that site's own data."
      />

      <section className="mx-auto max-w-7xl px-4 pb-12 sm:px-6 lg:px-8">
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Selection */}
          <Card className="lg:col-span-1 h-fit">
            <CardHeader>
              <CardTitle>Forecast settings</CardTitle>
              <CardDescription>Three steps to a forecast.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-3">
                <StepTitle n={1} title="Energy type" icon={Zap} />
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    className="flex flex-col items-center gap-1 rounded-lg border-2 border-primary bg-primary/5 p-3 text-sm font-medium text-foreground"
                    aria-pressed="true"
                  >
                    <Wind className="h-5 w-5 text-primary" />
                    Wind
                  </button>
                  <Link
                    href="/solar"
                    className="flex flex-col items-center gap-1 rounded-lg border border-dashed border-border p-3 text-sm text-muted-foreground hover:bg-muted"
                  >
                    <Sun className="h-5 w-5" />
                    Solar
                    <span className="text-[10px] uppercase tracking-wide">coming soon</span>
                  </Link>
                </div>
              </div>

              <div className="space-y-3">
                <StepTitle n={2} title="Site" icon={MapPin} />
                <Select value={site} onValueChange={setSite} disabled={!sites.length}>
                  <SelectTrigger aria-label="Site">
                    <SelectValue placeholder={loadError ? "Sites unavailable" : "Loading sites..."} />
                  </SelectTrigger>
                  <SelectContent>
                    {sites.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-3">
                <StepTitle n={3} title="Horizon" icon={Clock} />
                <div className="grid grid-cols-3 gap-2">
                  {HORIZONS.map((h) => (
                    <button
                      key={h}
                      type="button"
                      onClick={() => setHorizon(h)}
                      aria-pressed={horizon === h}
                      className={cn(
                        "rounded-md border px-2 py-2 text-sm font-medium transition-colors",
                        horizon === h ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted",
                      )}
                    >
                      {h} h
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">{HORIZON_LABELS[horizon]}</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="as-of" className="text-xs text-muted-foreground">
                  Issue time, UTC (optional; default is a fixed date in the test period)
                </Label>
                <input
                  id="as-of"
                  type="datetime-local"
                  step={3600}
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value.slice(0, 16))}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </div>

              <div className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
                {model ? (
                  <>
                    Model for {horizon} h: run <span className="font-mono">{model.run_id}</span>, promoted{" "}
                    {formatTimestamp(model.promoted_at)}
                  </>
                ) : (
                  <>No global model is registered for {horizon} h yet.</>
                )}
              </div>

              <Button className="w-full gap-2" onClick={handleForecast} disabled={!site || loading}>
                {loading ? (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-background border-t-transparent" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                {loading ? "Forecasting..." : "Get forecast"}
              </Button>
            </CardContent>
          </Card>

          {/* Result */}
          <div className="lg:col-span-2 space-y-4">
            {loadError != null && <ApiErrorNotice error={loadError} notConnectedTitle="Sites unavailable" />}
            {error != null && <ApiErrorNotice error={error} notConnectedTitle="Forecast not available yet" />}

            <Card>
              <CardHeader className="flex flex-row items-start justify-between gap-4">
                <div className="space-y-1.5">
                  <CardTitle>{result ? `${siteName}: ${result.horizon} h forecast` : "Forecast vs actual"}</CardTitle>
                  <CardDescription>
                    {result
                      ? `Issued at ${formatUtc(result.as_of)} by global model ${result.model.run_id}`
                      : "Pick a site and a horizon, then press Get forecast."}
                  </CardDescription>
                </div>
                {hasPower && (
                  <div className="flex rounded-md border border-border p-0.5 text-xs">
                    {(["speed", "power"] as const).map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => setView(v)}
                        className={cn("rounded px-2 py-1", view === v ? "bg-primary text-primary-foreground" : "text-muted-foreground")}
                      >
                        {v === "speed" ? "Speed" : "Power"}
                      </button>
                    ))}
                  </div>
                )}
              </CardHeader>
              <CardContent>
                {result ? (
                  <div className="h-[380px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                        <XAxis
                          dataKey="t"
                          type="number"
                          scale="time"
                          domain={["dataMin", "dataMax"]}
                          tickFormatter={tickFormat}
                          tick={{ fontSize: 11 }}
                        />
                        <YAxis tick={{ fontSize: 11 }} label={{ value: unit, angle: -90, position: "insideLeft", fontSize: 11 }} />
                        <Tooltip
                          labelFormatter={(t) => new Date(Number(t)).toUTCString()}
                          formatter={(v: number, name) => [`${v.toFixed(2)} ${unit}`, name]}
                        />
                        <Legend />
                        {asOfMs !== undefined && <ReferenceLine x={asOfMs} stroke="#888" strokeDasharray="4 4" label={{ value: "issue time", fontSize: 10 }} />}
                        <Line type="monotone" dataKey="actual" name="Actual" stroke="#A23B72" dot={false} strokeWidth={2} connectNulls />
                        <Line type="monotone" dataKey="forecast" name="Forecast" stroke="#2E86AB" dot={chartData.length < 3} strokeWidth={2} connectNulls />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="flex h-[380px] flex-col items-center justify-center text-center">
                    <Gauge className="h-12 w-12 text-muted-foreground mb-4" />
                    <h4 className="font-semibold text-foreground">No forecast yet</h4>
                    <p className="text-sm text-muted-foreground mt-1 max-w-xs">
                      The chart shows actual wind speed before and after the issue time, and the model&apos;s forecast after it.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>

            {result && (
              <div className="grid gap-4 sm:grid-cols-3">
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-xs text-muted-foreground">Forecast points</p>
                    <p className="text-2xl font-semibold">{result.forecast.length}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-xs text-muted-foreground">MAE vs actual</p>
                    <p className="text-2xl font-semibold">{errorStats ? `${errorStats.mae.toFixed(2)} ${result.unit}` : "—"}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-xs text-muted-foreground">RMSE vs actual</p>
                    <p className="text-2xl font-semibold">{errorStats ? `${errorStats.rmse.toFixed(2)} ${result.unit}` : "—"}</p>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        </div>
      </section>
    </PageLayout>
  )
}
