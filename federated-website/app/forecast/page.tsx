"use client"

// Forecast (DEMO_DAY_PLAN.md §2 E): power first. Every forecast comes from the newest promoted
// model for its energy type and horizon, shown in the model card above the chart.

import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { RefreshCw } from "lucide-react"
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { AppPage, Card, PageHeader, StatRow, StatTile } from "@/components/fw/surface"
import { Pill, TextAction } from "@/components/fw/button"
import { Segmented, Select } from "@/components/fw/form"
import { ApiError, EmptyState, Skeleton } from "@/components/fw/feedback"
import { StatusPill } from "@/components/fw/status"
import { fmtDateTime, fmtPct, fmtPower, fmtSigned, relTime } from "@/components/fw/format"
import { useAuth } from "@/lib/auth"
import {
  getForecast,
  getSites,
  listModels,
  listMySites,
  PlatformApiError,
  pointPower,
  pointValue,
  type EnergyType,
  type ForecastResponse,
  type RegisteredModel,
  type Site,
} from "@/lib/platform-api"

const HORIZONS = [
  { value: 1, label: "1 h" },
  { value: 72, label: "72 h" },
  { value: 432, label: "18 days" },
]

const QUANTITY: Record<EnergyType, { tab: string; unit: string; label: string }> = {
  wind: { tab: "Wind speed", unit: "m/s", label: "Wind speed" },
  solar: { tab: "Irradiance", unit: "W/m²", label: "Irradiance (GHI)" },
}

export default function ForecastPage() {
  return (
    <Suspense fallback={<AppPage><Skeleton className="h-96 w-full" /></AppPage>}>
      <Forecast />
    </Suspense>
  )
}

function Forecast() {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const { user, loading: authLoading } = useAuth()

  const energy: EnergyType = params.get("energy") === "solar" ? "solar" : "wind"
  const siteParam = params.get("site")

  const [sites, setSites] = useState<Site[] | null>(null)
  const [models, setModels] = useState<RegisteredModel[] | null>(null)
  const [data, setData] = useState<ForecastResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState<"power" | "quantity">("power")
  const [now, setNow] = useState(() => Date.now())

  const setParams = useCallback(
    (patch: Record<string, string | null>) => {
      const q = new URLSearchParams(params.toString())
      for (const [k, v] of Object.entries(patch)) {
        if (v === null) q.delete(k)
        else q.set(k, v)
      }
      router.replace(`${pathname}?${q}`, { scroll: false })
    },
    [params, pathname, router],
  )

  // Sites you may see forecasts for: lab sites, plants with public forecasts, plants you own (admins: every plant)
  useEffect(() => {
    if (authLoading) return
    let cancelled = false
    ;(async () => {
      try {
        const [pub, mine] = await Promise.all([getSites(energy), user ? listMySites().catch(() => []) : Promise.resolve([])])
        const own = mine.filter((s) => s.kind === "plant" && s.status === "active" && s.energy_type === energy)
        const publicPlants = pub.filter((s) => s.kind === "plant" && s.forecast_public && !own.some((o) => o.id === s.id))
        const lab = pub.filter((s) => s.kind !== "plant")
        if (!cancelled) setSites([...own, ...publicPlants, ...lab])
      } catch (e) {
        if (!cancelled) {
          setSites([])
          setError(e)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [energy, user, authLoading])

  useEffect(() => {
    listModels().then(setModels).catch(() => setModels([]))
  }, [data?.model.run_id])

  const site = useMemo(() => sites?.find((s) => s.id === siteParam) ?? sites?.[0] ?? null, [sites, siteParam])
  const available = useMemo(() => new Set((models ?? []).filter((m) => m.energy_type === energy).map((m) => m.horizon)), [models, energy])
  // No horizon chosen: 72 h if a model serves it, else the shortest one that has a model
  const horizon = Number(params.get("horizon")) || (available.has(72) || !available.size ? 72 : Math.min(...available))
  const ready = Boolean(params.get("horizon")) || models !== null

  const load = useCallback(async () => {
    if (!site || !ready) return
    setLoading(true)
    setError(null)
    try {
      setData(await getForecast({ energyType: energy, site: site.id, horizon }))
      setNow(Date.now())
    } catch (e) {
      setData(null)
      setError(e)
    } finally {
      setLoading(false)
    }
  }, [site, energy, horizon, ready])

  useEffect(() => {
    load()
  }, [load])

  // Quietly follow promotions: refetch every minute
  useEffect(() => {
    const t = setInterval(() => {
      if (document.visibilityState === "visible") load()
    }, 60_000)
    return () => clearInterval(t)
  }, [load])

  const plants = sites?.filter((s) => s.kind === "plant") ?? []
  const lab = sites?.filter((s) => s.kind !== "plant") ?? []

  return (
    <AppPage>
      <PageHeader
        label="Forecast"
        title="Power forecasts"
        description="From the newest shared model of the federation. It was trained on every site's data without that data leaving the site."
        actions={
          <Pill variant="outline" size="s" icon={<RefreshCw className="h-4 w-4" />} onClick={load} loading={loading}>
            Refresh
          </Pill>
        }
      />

      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <div className="fw-label mb-2">Energy</div>
            <Segmented
              ariaLabel="Energy type"
              value={energy}
              onChange={(v) => {
                setData(null)
                setSites(null)
                setParams({ energy: v, site: null })
              }}
              options={[
                { value: "wind" as EnergyType, label: "Wind" },
                { value: "solar" as EnergyType, label: "Solar" },
              ]}
            />
          </div>
          <div className="w-[280px] max-w-full">
            <label htmlFor="site" className="fw-label mb-2 block">
              Site
            </label>
            <Select id="site" value={site?.id ?? ""} onChange={(e) => setParams({ site: e.target.value })} disabled={!sites?.length}>
              {plants.length > 0 && (
                <optgroup label="Plants">
                  {plants.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label="Lab sites">
                {lab.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </optgroup>
            </Select>
          </div>
        </div>
        <div>
          <div className="fw-label mb-2">Horizon</div>
          <Segmented
            ariaLabel="Forecast horizon"
            value={horizon}
            onChange={(v) => setParams({ horizon: String(v) })}
            options={HORIZONS.map((h) => ({
              ...h,
              title: available.size && !available.has(h.value) ? "No model promoted for this horizon yet" : undefined,
            }))}
          />
        </div>
      </div>

      {error ? (
        <ForecastError error={error} horizon={horizon} energy={energy} available={[...available]} onPick={(h) => setParams({ horizon: String(h) })} onRetry={load} />
      ) : !data || !site ? (
        <div className="space-y-6">
          <Skeleton className="h-[88px] w-full rounded-[16px]" />
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
          <Skeleton className="h-[420px] w-full rounded-[16px]" />
        </div>
      ) : (
        <ForecastView data={data} site={site} tab={tab} setTab={setTab} now={now} />
      )}
    </AppPage>
  )
}

function ForecastError({
  error,
  horizon,
  energy,
  available,
  onPick,
  onRetry,
}: {
  error: unknown
  horizon: number
  energy: EnergyType
  available: number[]
  onPick: (h: number) => void
  onRetry: () => void
}) {
  const noModel = error instanceof PlatformApiError && (error.status === 404 || error.notConnected) && /model|promot/i.test(error.message)
  if (noModel) {
    return (
      <Card>
        <EmptyState
          title={`No ${energy} model for ${horizon === 432 ? "18 days" : `${horizon} h`} yet`}
          action={
            available.length ? (
              <div className="flex flex-wrap justify-center gap-2">
                {available.sort((a, b) => a - b).map((h) => (
                  <Pill key={h} variant="outline" size="s" onClick={() => onPick(h)}>
                    Show {h === 432 ? "18 days" : `${h} h`}
                  </Pill>
                ))}
              </div>
            ) : undefined
          }
        >
          An admin chooses which finished training run serves forecasts (Training → a run → Use for forecasts).
        </EmptyState>
      </Card>
    )
  }
  return <ApiError error={error} notConnected="Forecasts aren't available right now" onRetry={onRetry} />
}

// -------------------------------------------------------------------------------------------------

type Row = {
  t: number
  actual?: number | null
  forecast?: number | null
  band?: [number, number] | null
  clear?: number | null
}

function ForecastView({
  data,
  site,
  tab,
  setTab,
  now,
}: {
  data: ForecastResponse
  site: Site
  tab: "power" | "quantity"
  setTab: (t: "power" | "quantity") => void
  now: number
}) {
  const e = data.energy_type
  const cap = data.capacity_kw ?? null
  const q = QUANTITY[e]

  const rows: Row[] = useMemo(() => {
    const pick = (p: (typeof data.actual)[number]) => (tab === "power" ? pointPower(p, e) : pointValue(p, e))
    const scale = (v: number | null) => (v == null ? null : tab === "power" ? v / 1000 : v)
    const actual = data.actual.map((p) => ({ t: new Date(p.timestamp).getTime(), actual: scale(pick(p)), clear: tab === "quantity" && e === "solar" ? p.clear_sky_ghi ?? null : null }))
    const fc = data.forecast.map((p) => ({ t: new Date(p.timestamp).getTime(), forecast: scale(pick(p)), clear: tab === "quantity" && e === "solar" ? p.clear_sky_ghi ?? null : null }))
    const last = actual[actual.length - 1]
    if (last && last.actual != null) Object.assign(last, { forecast: last.actual })
    return [...actual, ...fc]
  }, [data, tab, e])

  const powers = data.forecast.map((p) => pointPower(p, e)).filter((v): v is number => v != null)
  const next = data.forecast[0]
  const nextPower = next ? pointPower(next, e) : null
  const peakIdx = powers.length ? powers.indexOf(Math.max(...powers)) : -1
  const peak = peakIdx >= 0 ? data.forecast[peakIdx] : null
  const meanCf = cap && powers.length ? powers.reduce((a, b) => a + b, 0) / powers.length / cap : null
  const asOf = new Date(data.as_of).getTime()
  const capMw = cap ? cap / 1000 : undefined
  const yMax = tab === "power" ? capMw : undefined

  return (
    <div className="space-y-8">
      {data.summary && (
        <p className="mb-4 rounded-[12px] bg-paper-warm px-4 py-3 text-[15px] leading-6 text-ink">
          {data.summary.text}
          <span className="ml-2 text-xs text-fw-muted">{data.summary.source === "claude" ? "Summary written by Claude" : "Summary"}</span>
        </p>
      )}
      <ModelCard data={data} now={now} />

      <StatRow className="mb-0">
        <StatTile label="Next hour" value={fmtPower(nextPower)} hint={next?.capacity_factor != null ? `${fmtPct(next.capacity_factor)} of capacity` : fmtDateTime(next?.timestamp)} />
        <StatTile
          label={`Peak, next ${data.horizon === 432 ? "18 days" : `${data.horizon} h`}`}
          value={fmtPower(peak ? pointPower(peak, e) : null)}
          hint={peak ? fmtDateTime(peak.timestamp) : undefined}
        />
        <StatTile label="Mean capacity factor" value={fmtPct(meanCf)} hint="over the forecast" />
        <StatTile
          label="Capacity"
          value={fmtPower(cap)}
          hint={data.power_basis === "plant" ? "registered plant" : e === "wind" ? "2 MW reference turbine" : "1 MW reference PV"}
        />
      </StatRow>

      <Card
        title={
          <div className="flex flex-wrap items-center gap-2">
            <span>{site.name}</span>
            {site.kind === "plant" ? <StatusPill tone="none">Plant</StatusPill> : <StatusPill tone="none">Lab site</StatusPill>}
          </div>
        }
        action={
          <Segmented
            size="s"
            ariaLabel="Chart"
            value={tab}
            onChange={setTab}
            options={[
              { value: "power" as const, label: "Power" },
              { value: "quantity" as const, label: q.tab },
            ]}
          />
        }
      >
        <div className="mb-4 flex flex-wrap gap-x-5 gap-y-1 text-sm text-fw-muted">
          <Legend swatch="bg-ink" label="Measured" />
          <Legend swatch="bg-fw-accent" label="Forecast" />
          {tab === "quantity" && e === "solar" && <Legend swatch="border-t border-dashed border-fw-muted bg-transparent" label="Clear sky" />}
          <span className="fw-num ml-auto text-xs">issued {fmtDateTime(data.as_of, { utc: true })}</span>
        </div>
        <div className="h-[360px] sm:h-[420px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: tab === "power" && capMw ? 8 : 16, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="fc-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ff3f10" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="#ff3f10" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="rgba(34,34,34,0.06)" />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(t) => new Date(t).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit" })}
                tick={{ fontSize: 12, fill: "#737373" }}
                axisLine={false}
                tickLine={false}
                minTickGap={48}
              />
              <YAxis
                yAxisId="v"
                domain={[0, yMax ?? "auto"]}
                tick={{ fontSize: 12, fill: "#737373", fontFamily: "var(--font-mono)" }}
                axisLine={false}
                tickLine={false}
                width={56}
                tickFormatter={(v) => (tab === "power" ? `${+v.toFixed(1)}` : `${Math.round(v)}`)}
                label={{ value: tab === "power" ? "MW" : q.unit, position: "insideTopLeft", offset: 0, dy: -4, fontSize: 11, fill: "#737373" }}
              />
              {tab === "power" && capMw && (
                <YAxis
                  yAxisId="cf"
                  orientation="right"
                  domain={[0, 100]}
                  ticks={[0, 25, 50, 75, 100]}
                  tickFormatter={(v) => `${v}%`}
                  tick={{ fontSize: 12, fill: "#737373", fontFamily: "var(--font-mono)" }}
                  axisLine={false}
                  tickLine={false}
                  width={44}
                />
              )}
              <Tooltip content={<ChartTip unit={tab === "power" ? "MW" : q.unit} capMw={tab === "power" ? capMw : undefined} />} />
              <ReferenceLine yAxisId="v" x={asOf} stroke="#222" strokeOpacity={0.45} strokeDasharray="3 4" label={{ value: "now", position: "insideTopRight", fontSize: 11, fill: "#737373" }} />
              <Area yAxisId="v" dataKey="forecast" type="monotone" stroke="none" fill="url(#fc-fill)" isAnimationActive={false} connectNulls />
              {tab === "quantity" && e === "solar" && (
                <Line yAxisId="v" dataKey="clear" type="monotone" stroke="#737373" strokeDasharray="4 4" strokeWidth={1.25} dot={false} isAnimationActive={false} connectNulls />
              )}
              <Line yAxisId="v" dataKey="actual" type="monotone" stroke="#222" strokeWidth={1.75} dot={false} isAnimationActive={false} />
              <Line
                yAxisId="v"
                dataKey="forecast"
                type="monotone"
                stroke="#ff3f10"
                strokeWidth={2.5}
                dot={data.forecast.length <= 2 ? { r: 4, fill: "#ff3f10", strokeWidth: 0 } : false}
                isAnimationActive={false}
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-4 text-sm leading-5 text-fw-muted">
          {data.source === "central"
            ? `Forecast on the ArqauQuat server from the last hours of ${e === "wind" ? "wind speed" : "irradiance"} this plant shares for central forecasting. `
            : data.source === "local"
              ? "Forecast made at the plant with the downloaded model; the plant keeps its data and sent only this forecast. "
              : "Lab site: forecast next to its data, as a plant with its own inference would. "}
          {data.stored_at ? `Updated ${relTime(data.stored_at)}. ` : ""}
          {e === "wind"
            ? data.power_basis === "plant"
              ? "Power from the plant's turbines (count × rated power, generic power curve)."
              : "Power of a 2 MW reference turbine (generic power curve)."
            : data.power_basis === "plant"
              ? "PV power from the plant's capacity (performance ratio 0.8)."
              : "PV power of a 1 MW reference plant (performance ratio 0.8)."}
        </p>
      </Card>

      <ForecastTable data={data} />
    </div>
  )
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-0.5 w-5 rounded-full ${swatch}`} aria-hidden />
      {label}
    </span>
  )
}

function ChartTip({ active, payload, label, unit, capMw }: { active?: boolean; payload?: { dataKey: string; value: number }[]; label?: number; unit: string; capMw?: number }) {
  if (!active || !payload?.length || label == null) return null
  const get = (k: string) => payload.find((p) => p.dataKey === k && p.value != null)?.value
  const a = get("actual")
  const f = get("forecast")
  const c = get("clear")
  const fmt = (v: number) => `${unit === "MW" ? v.toFixed(2) : v.toFixed(1)} ${unit}${capMw ? ` · ${Math.round((v / capMw) * 100)} %` : ""}`
  return (
    <div className="rounded-[12px] border border-line bg-white px-3 py-2 text-sm shadow-[0_12px_32px_rgba(34,34,34,0.12)]">
      <div className="fw-num mb-1 text-xs text-fw-muted">{new Date(label).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div>
      {a != null && <div>Measured <span className="fw-num">{fmt(a)}</span></div>}
      {f != null && a == null && <div className="text-fw-accent-dark">Forecast <span className="fw-num">{fmt(f)}</span></div>}
      {c != null && <div className="text-fw-muted">Clear sky <span className="fw-num">{c.toFixed(0)} W/m²</span></div>}
    </div>
  )
}

function ModelCard({ data, now }: { data: ForecastResponse; now: number }) {
  const m = data.model
  const energy = data.energy_type === "solar" ? "solar" : "wind"
  const skill = m.skill_vs_persistence
  return (
    <section aria-label="Model behind this forecast" className="rounded-[16px] bg-paper-warm px-6 py-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <div className="fw-label">Model</div>
          <div className="mt-1 text-xl font-medium tracking-[-0.01em] text-ink">
            Global {energy} model{" "}
            <span className="font-normal text-fw-muted">
              · {m.horizon === 432 ? "18 days" : `${m.horizon ?? data.horizon} h`} ahead
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fw-muted">
            <span className="fw-num text-ink" title="Training run">
              {m.run_id}
            </span>
            <span title={m.sites.join(", ")}>{m.sites.length} sites</span>
            {m.rounds_completed != null && <span>{m.rounds_completed} {m.rounds_completed === 1 ? "round" : "rounds"}</span>}
            {m.strategy && <span className="uppercase">{m.strategy}</span>}
            <span title={m.skill_reference ?? "1 − MAE(model) / MAE(persistence), test split"}>
              skill <span className="fw-num text-ink">{fmtSigned(skill)}</span> vs persistence
            </span>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2 md:items-end">
          <div className="flex flex-wrap gap-1.5 md:justify-end">
            {m.data_percent != null && m.data_percent < 100 && (
              <StatusPill tone="none" title="A short training run for the demo; full runs use all the data">
                Demo model · {m.data_percent} % of the data
              </StatusPill>
            )}
            <StatusPill tone="accent">{m.version ? `v${m.version} · ` : ""}Serving forecasts</StatusPill>
          </div>
          <span className="text-sm text-fw-muted">
            promoted {relTime(m.promoted_at, now)}
            {m.promoted_by ? ` by ${m.promoted_by}` : ""}
          </span>
          <TextAction href={`/training/${encodeURIComponent(m.run_id)}`} tone="muted">
            Open run
          </TextAction>
        </div>
      </div>
    </section>
  )
}

function ForecastTable({ data }: { data: ForecastResponse }) {
  const [open, setOpen] = useState(false)
  const e = data.energy_type
  const q = QUANTITY[e]
  const rows = data.forecast
  return (
    <Card
      title="Forecast values"
      action={
        <TextAction onClick={() => setOpen((v) => !v)} arrow={false}>
          {open ? "Hide" : `Show ${rows.length} ${rows.length === 1 ? "hour" : "hours"}`}
        </TextAction>
      }
    >
      {open ? (
        <div className="-mx-6 max-h-[420px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white">
              <tr>
                {["Time (UTC)", "Power", "% capacity", q.label].map((h, i) => (
                  <th key={h} className={`fw-label h-10 border-b border-line px-3 first:pl-6 last:pr-6 ${i ? "text-right" : "text-left"}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.timestamp} className="border-b border-line last:border-0">
                  <td className="fw-num h-10 px-3 pl-6">{fmtDateTime(p.timestamp, { utc: true })}</td>
                  <td className="fw-num px-3 text-right">{fmtPower(pointPower(p, e), 2)}</td>
                  <td className="fw-num px-3 text-right">{fmtPct(p.capacity_factor, 1)}</td>
                  <td className="fw-num px-3 pr-6 text-right">
                    {pointValue(p, e)?.toFixed(e === "wind" ? 2 : 0) ?? "—"} {q.unit}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-fw-muted">Hourly power, capacity factor and {q.label.toLowerCase()} for the whole horizon.</p>
      )}
    </Card>
  )
}
