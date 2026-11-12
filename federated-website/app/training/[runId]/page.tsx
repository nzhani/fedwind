"use client"

// One run on the training dashboard (plan T3.7, FR-24): status, round X of N, validation
// error per round, how each site took part, payload size and round time. Polls while active.

import Link from "next/link"
import { useParams } from "next/navigation"
import { useCallback, useEffect, useState } from "react"
import { ArrowLeft, Award, CircleStop, Clock, Network, Upload } from "lucide-react"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { PageLayout } from "@/components/page-layout"
import { ApiErrorNotice, ErrorNotice, RunStatusBadge, formatDuration, formatTimestamp } from "@/components/platform"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  formatBytes,
  getRun,
  promoteModel,
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
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<RunDetail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [promoted, setPromoted] = useState<RegisteredModel | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setRun(await getRun(runId))
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

  return (
    <PageLayout>
      <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
        <Link href="/training" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
          All runs
        </Link>

        {error != null && <ApiErrorNotice error={error} notConnectedTitle="Not connected" />}
        {actionError && <ErrorNotice message={actionError} />}

        {run && (
          <>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <h1 className="font-mono text-lg font-semibold break-all">{run.run_id}</h1>
                  <RunStatusBadge status={run.status} />
                </div>
                <p className="text-sm text-muted-foreground">
                  {run.strategy.toUpperCase()} · horizon {run.horizon} h · {run.sites.length} sites · created{" "}
                  {formatTimestamp(run.created_at)}
                  {run.finished_at && <> · finished {formatTimestamp(run.finished_at)}</>}
                </p>
              </div>
              <div className="flex gap-2">
                {active && (
                  <Button variant="outline" className="gap-2" disabled={busy} onClick={() => act(() => stopRun(run.run_id))}>
                    <CircleStop className="h-4 w-4" />
                    Stop run
                  </Button>
                )}
                {run.status === "done" && (
                  <Button
                    className="gap-2"
                    disabled={busy}
                    onClick={() => act(async () => setPromoted(await promoteModel(run.run_id)))}
                  >
                    <Award className="h-4 w-4" />
                    Use for forecasts
                  </Button>
                )}
              </div>
            </div>

            {run.error && <ErrorNotice title={`Run ${run.status}`} message={run.error} />}
            {promoted && (
              <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800">
                This run is now the global model for {promoted.horizon} h forecasts.{" "}
                <Link href="/forecast" className="font-medium underline">
                  Open Forecast
                </Link>
              </div>
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
                    {hasReal ? "MAE in m/s (real units) and on normalized values." : "On normalized values."}
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
                          {hasReal && <Line type="monotone" dataKey="real_mae" name="MAE (m/s)" stroke="#A23B72" strokeWidth={2} dot={history.length < 30} />}
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
                  <CardDescription>Test-split metrics of the best round, written by the server.</CardDescription>
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
