"use client"

// Training dashboard, run list (plan T3.7, FR-24). Read-only: runs are started from /experiments.

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { Activity, FlaskConical, RefreshCw, Server } from "lucide-react"
import { PageLayout } from "@/components/page-layout"
import { ApiErrorNotice, NotConnectedNotice, PageHeader, RunStatusBadge, formatTimestamp } from "@/components/platform"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { getFederation, listRuns, type FederationStatus, type RunListResponse } from "@/lib/platform-api"

const POLL_MS = 10_000

export default function TrainingPage() {
  const [runs, setRuns] = useState<RunListResponse | null>(null)
  const [federation, setFederation] = useState<FederationStatus | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    setRefreshing(true)
    try {
      const [r, f] = await Promise.all([listRuns(), getFederation()])
      setRuns(r)
      setFederation(f)
      setError(null)
    } catch (err) {
      setError(err)
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  return (
    <PageLayout>
      <PageHeader
        badge="Training"
        title="Federated Training Dashboard"
        description="Every federated run on the wind sites: its status, the current round and how each site took part."
      />

      <section className="mx-auto max-w-7xl px-4 pb-12 sm:px-6 lg:px-8 space-y-6">
        {error != null && <ApiErrorNotice error={error} notConnectedTitle="Not connected" />}

        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardContent className="pt-6 flex items-start gap-3">
              <Server className="h-5 w-5 text-primary mt-0.5" />
              <div>
                <p className="text-xs text-muted-foreground">Federation</p>
                <p className="font-semibold">
                  {federation == null ? "—" : federation.connected ? "Connected" : "Not connected"}
                </p>
                {federation?.connected && federation.connected_nodes != null && (
                  <p className="text-xs text-muted-foreground">{federation.connected_nodes} clients connected</p>
                )}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 flex items-start gap-3">
              <Activity className="h-5 w-5 text-primary mt-0.5" />
              <div>
                <p className="text-xs text-muted-foreground">Active run</p>
                {runs?.active_run_id ? (
                  <Link href={`/training/${runs.active_run_id}`} className="font-mono text-sm text-primary hover:underline break-all">
                    {runs.active_run_id}
                  </Link>
                ) : (
                  <p className="font-semibold">None</p>
                )}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 flex items-start gap-3">
              <FlaskConical className="h-5 w-5 text-primary mt-0.5" />
              <div>
                <p className="text-xs text-muted-foreground">Runs recorded</p>
                <p className="font-semibold">{runs ? runs.runs.length : "—"}</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {federation && !federation.connected && (
          <NotConnectedNotice title="Federation not connected" message={federation.detail}>
            <p className="text-sm text-amber-800">
              Runs that already exist in the runs folder are still listed below.
            </p>
          </NotConnectedNotice>
        )}

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div className="space-y-1.5">
              <CardTitle>Runs</CardTitle>
              <CardDescription>Newest first. Updates every 10 seconds.</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={load} disabled={refreshing} className="gap-2 bg-transparent">
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </CardHeader>
          <CardContent>
            {runs && runs.runs.length === 0 ? (
              <div className="py-12 text-center">
                <h4 className="font-semibold text-foreground">No runs yet</h4>
                <p className="text-sm text-muted-foreground mt-1">
                  Start one from the{" "}
                  <Link href="/experiments" className="text-primary hover:underline">
                    Experiments
                  </Link>{" "}
                  page.
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Strategy</TableHead>
                    <TableHead>Horizon</TableHead>
                    <TableHead className="w-40">Progress</TableHead>
                    <TableHead>Sites</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs?.runs.map((r) => (
                    <TableRow key={r.run_id}>
                      <TableCell>
                        <Link href={`/training/${r.run_id}`} className="font-mono text-xs text-primary hover:underline">
                          {r.run_id}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <RunStatusBadge status={r.status} />
                      </TableCell>
                      <TableCell className="uppercase text-xs">{r.strategy}</TableCell>
                      <TableCell>{r.horizon} h</TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <Progress value={r.total_rounds ? (100 * r.current_round) / r.total_rounds : 0} className="h-1.5" />
                          <p className="text-xs text-muted-foreground">
                            Round {r.current_round} of {r.total_rounds}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>{r.sites.length}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatTimestamp(r.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </section>
    </PageLayout>
  )
}
