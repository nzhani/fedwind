"use client"

// One run on the training dashboard (plan T3.7, FR-24): status, round X of N, validation
// error per round, how each site took part, payload size and round time. Polls while active.

import Link from "next/link"
import { useParams } from "next/navigation"
import { useCallback, useEffect, useState } from "react"
import { ArrowLeft, Award, CircleStop, Clock, Network, Upload } from "lucide-react"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { PageLayout } from "@/components/page-layout"
import { Pill, TextAction } from "@/components/fw/button"
import { Notice } from "@/components/fw/feedback"
import { RunPill, StatusPill } from "@/components/fw/status"
import { useAuth } from "@/lib/auth"
import { ApiErrorNotice, ErrorNotice, RunStatusBadge, formatDuration, formatTimestamp } from "@/components/platform"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  ENERGY_TYPES,
  displayUnit,
  runEnergyType,
  formatBytes,
  getRun,
  promoteModel,
  listModels,
  stopRun,
  type RegisteredModel,
  type RunDetail,
} from "@/lib/platform-api"

const POLL_MS = 5_000

function Stat({ icon: Icon, label, value }: { icon: typeof Clock; label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-6 flex items-start gap-3">
        <Icon className="h-5 w-5 text-primary mt-0.5" />
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="font-semibold">{value}</p>
        </div>
      </CardContent>
    </Card>
  )
}

const fmt = (v: number | null | undefined, digits = 3) => (v == null ? "—" : v.toFixed(digits))

export default function RunPage() {
  const { isAdmin } = useAuth()
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<RunDetail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [promoted, setPromoted] = useState<RegisteredModel | null>(null)
  const [serving, setServing] = useState<RegisteredModel | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [r, models] = await Promise.all([getRun(runId), listModels().catch(() => [] as RegisteredModel[])])
      setRun(r)
      setServing(models.find((m) => m.run_id === runId) ?? null)
      setError(null)
    } catch (err) {
      setError(err)
    }
  }, [runId])

  const active = run?.status === "running" || run?.status === "queued"

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!active) return
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [active, load])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setActionError(null)
    try {
      await fn()
      await load()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const history = run?.history ?? []
  const last = history.at(-1)
  const hasReal = history.some((m) => m.val_real?.mae != null)
  const chartData = history.map((m) => ({
    round: m.round,
    val_mae: m.val?.mae,
    val_rmse: m.val?.rmse,
    real_mae: m.val_real?.mae,
  }))
  const durations = history.map((m) => m.duration_s).filter((d): d is number => d != null)
  const meanRound = durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : null

  // Every configured site, with its status in the latest round if it reported.
  const siteRows = (run?.sites ?? []).map((site) => ({ site, ...run?.clients.find((c) => c.site === site) }))
  const realMetrics = run?.result?.metrics?.real
  const perSite = run?.result?.metrics?.per_site
  const energy = runEnergyType(run?.config)
  const energyInfo = ENERGY_TYPES.find((e) => e.value === energy)!
  const unit = displayUnit(last?.val_real?.unit ?? run?.result?.unit) || energyInfo.unit

  return (
    <PageLayout>
      <section className="mx-auto max-w-[1280px] px-5 pb-24 pt-8 sm:px-10 space-y-6">
        <Link href="/training" className="inline-flex items-center gap-1.5 text-sm font-medium text-fw-muted hover:text-ink">
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} />
          All runs
        </Link>

        {error != null && <ApiErrorNotice error={error} notConnectedTitle="Not connected" />}
        {actionError && <ErrorNotice message={actionError} />}

        {run && (
          <>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-3">
                <div className="fw-label">Training run</div>
                <h1 className="fw-num break-all text-[28px] leading-[1.15] tracking-[-0.02em] sm:text-[36px]">{run.run_id}</h1>
                <div className="flex flex-wrap items-center gap-2">
                  <RunPill status={run.status} />
                  {serving && (
                    <StatusPill tone="accent" title={`Promoted ${formatTimestamp(serving.promoted_at)}${serving.promoted_by ? ` by ${serving.promoted_by}` : ""}`}>
                      Currently serving {serving.horizon} h {serving.energy_type} forecasts
                    </StatusPill>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {energyInfo.label} · {run.strategy.toUpperCase()} · horizon {run.horizon} h · {run.sites.length} sites · created{" "}
                  {formatTimestamp(run.created_at)}
                  {run.finished_at && <> · finished {formatTimestamp(run.finished_at)}</>}
                </p>
              </div>
              <div className="flex gap-2">
                {active && isAdmin && (
                  <Pill variant="danger" icon={<CircleStop className="h-4 w-4" />} disabled={busy} onClick={() => act(() => stopRun(run.run_id))}>
                    Stop run
                  </Pill>
                )}
                {run.status === "done" && isAdmin && !serving && (
                  <Pill icon={<Award className="h-4 w-4" />} loading={busy} onClick={() => act(async () => setPromoted(await promoteModel(run.run_id)))}>
                    Use for forecasts
                  </Pill>
                )}
              </div>
            </div>

            {run.error && <ErrorNotice title={`Run ${run.status}`} message={run.error} />}
            {promoted && (
              <Notice
                title={`This run now serves every ${promoted.energy_type} forecast ${promoted.horizon} h ahead`}
                action={<TextAction href={`/forecast?energy=${promoted.energy_type}&horizon=${promoted.horizon}`}>Open forecast</TextAction>}
              >
                Plants and lab sites switch to it on their next forecast.
              </Notice>
            )}

            <Card>
              <CardContent className="pt-6 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="font-medium">
                    Round {run.current_round} of {run.total_rounds}
                  </span>
                  {active && <span className="text-muted-foreground">updates every 5 s</span>}
                </div>
                <Progress value={run.total_rounds ? (100 * run.current_round) / run.total_rounds : 0} />
              </CardContent>
            </Card>

            <div className="grid gap-4 md:grid-cols-4">
              <Stat icon={Clock} label="Mean round time" value={formatDuration(meanRound)} />
              <Stat icon={Upload} label="Uplink, last round" value={formatBytes(last?.uplink_bytes)} />
              <Stat icon={Network} label="Sites replied, last round" value={last ? `${last.clients.filter((c) => c.status === "replied").length} of ${run.sites.length}` : "—"} />
              <Stat icon={Award} label="Best round" value={run.result?.best_round != null ? String(run.result.best_round) : "—"} />
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle>Validation error per round</CardTitle>
                  <CardDescription>
                    {hasReal
                      ? `MAE in ${unit} (real units${energy === "solar" ? ", daylight hours" : ""}) and on normalized values.`
                      : "On normalized values."}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {history.length ? (
                    <div className="h-[300px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                          <XAxis dataKey="round" tick={{ fontSize: 11 }} allowDecimals={false} />
                          <YAxis tick={{ fontSize: 11 }} />
                          <Tooltip formatter={(v: number) => v.toFixed(4)} />
                          <Legend />
                          {hasReal && <Line type="monotone" dataKey="real_mae" name={`MAE (${unit})`} stroke="#A23B72" strokeWidth={2} dot={history.length < 30} />}
                          <Line type="monotone" dataKey="val_mae" name="MAE (normalized)" stroke="#2E86AB" strokeWidth={2} dot={history.length < 30} />
                          <Line type="monotone" dataKey="val_rmse" name="RMSE (normalized)" stroke="#F18F01" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="py-16 text-center text-sm text-muted-foreground">No round has finished yet.</p>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Sites</CardTitle>
                  <CardDescription>{last ? `In round ${last.round}` : "No round reported yet"}</CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Site</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Samples</TableHead>
                        <TableHead className="text-right">Loss</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {siteRows.map((c) => (
                        <TableRow key={c.site}>
                          <TableCell className="capitalize">{c.site}</TableCell>
                          <TableCell>
                            {c.status === "replied" ? (
                              <span className="text-green-700 text-xs font-medium">replied</span>
                            ) : c.status === "dropped" ? (
                              <span className="text-red-700 text-xs font-medium">dropped</span>
                            ) : (
                              <span className="text-muted-foreground text-xs">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right text-xs">{c.num_examples ?? "—"}</TableCell>
                          <TableCell className="text-right text-xs">{fmt(c.train_loss)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>

            {run.result && run.status === "done" && (
              <Card>
                <CardHeader>
                  <CardTitle>Final result</CardTitle>
                  <CardDescription>
                    Test-split metrics of the best round, written by the server, in {unit}
                    {energy === "solar" ? " (daylight hours unless marked “all hours”)" : ""}.
                    {run.result.metrics?.reference ? ` Skill reference: ${run.result.metrics.reference}.` : ""}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {realMetrics && (
                    <div className="grid gap-4 sm:grid-cols-5">
                      {Object.entries(realMetrics).map(([k, v]) => (
                        <div key={k}>
                          <p className="text-xs uppercase text-muted-foreground">{k.replaceAll("_", " ")}</p>
                          <p className="text-lg font-semibold">{fmt(v)}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  {perSite && (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Site</TableHead>
                          {Object.keys(Object.values(perSite)[0] ?? {}).map((k) => (
                            <TableHead key={k} className="text-right uppercase">
                              {k.replaceAll("_", " ")}
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {Object.entries(perSite).map(([site, m]) => (
                          <TableRow key={site}>
                            <TableCell className="capitalize">{site}</TableCell>
                            {Object.values(m).map((v, i) => (
                              <TableCell key={i} className="text-right">
                                {fmt(v)}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            )}

            <details className="rounded-lg border border-border bg-card p-4 text-sm">
              <summary className="cursor-pointer font-medium">Run config</summary>
              <pre className="mt-3 overflow-x-auto text-xs text-muted-foreground">{JSON.stringify(run.config, null, 2)}</pre>
            </details>
          </>
        )}
      </section>
    </PageLayout>
  )
}
