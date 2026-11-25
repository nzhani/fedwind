"use client"

// Solar overview (FR-01, FR-06, FR-08, DR-02): the solar sites, how solar forecasting works,
// and which global solar models exist. Forecasts and runs use the same pages as wind
// (/forecast?energy=solar, /experiments?energy=solar).

import Link from "next/link"
import { useEffect, useState } from "react"
import { CloudSun, LineChart as LineChartIcon, MapPin, Moon, Play, Sun, Target } from "lucide-react"
import { PageLayout } from "@/components/page-layout"
import { ApiErrorNotice, PageHeader, formatTimestamp } from "@/components/platform"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { HORIZONS, getSites, listModels, type RegisteredModel, type Site } from "@/lib/platform-api"

const STEPS = [
  {
    icon: Sun,
    title: "Sun position",
    text: "Computed from each site's coordinates and the UTC hour, so the daily and yearly cycle never has to be learned.",
  },
  {
    icon: CloudSun,
    title: "Clear-sky index k*",
    text: "k* = GHI ÷ clear-sky GHI. The model forecasts k* (the clouds); multiplying by the clear-sky GHI of each future hour gives GHI again.",
  },
  {
    icon: Moon,
    title: "Daylight-only loss",
    text: "Night hours stay in the input so the series is continuous, but only daylight hours (sun above 5°) count in training and in the main errors.",
  },
  {
    icon: Target,
    title: "Honest baselines",
    text: "Every run is compared with smart persistence (k* now × clear sky later), plain persistence and climatology on the same test windows.",
  },
]

export default function SolarPage() {
  const [sites, setSites] = useState<Site[]>([])
  const [models, setModels] = useState<RegisteredModel[]>([])
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    getSites("solar").then(setSites).catch(setError)
    listModels()
      .then((m) => setModels(m.filter((x) => x.energy_type === "solar")))
      .catch(() => setModels([]))
  }, [])

  return (
    <PageLayout>
      <PageHeader
        badge="Solar"
        title="Solar Irradiance Forecasting"
        description="Five solar sites train one global model for irradiance (GHI) with the same federated LLM as wind. Each site keeps its data; only model updates travel."
      />

      <section className="mx-auto max-w-7xl px-4 pb-12 sm:px-6 lg:px-8 space-y-6">
        {error != null && <ApiErrorNotice error={error} notConnectedTitle="Solar sites unavailable" />}

        <div className="flex flex-wrap gap-3">
          <Button asChild className="gap-2">
            <Link href="/forecast?energy=solar">
              <LineChartIcon className="h-4 w-4" />
              Solar forecast
            </Link>
          </Button>
          <Button asChild variant="outline" className="gap-2">
            <Link href="/experiments?energy=solar">
              <Play className="h-4 w-4" />
              Start a solar run
            </Link>
          </Button>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s) => (
            <Card key={s.title}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <s.icon className="h-5 w-5 text-primary" />
                  {s.title}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{s.text}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MapPin className="h-5 w-5 text-primary" />
                Solar sites
              </CardTitle>
              <CardDescription>
                Cities near existing Kazakh PV plants (approximate coordinates). NASA POWER hourly irradiance, 2015–2024, UTC.
                Power uses an assumed 1 MW plant with a performance ratio of 0.8.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Site</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead className="text-right">Capacity</TableHead>
                    <TableHead className="text-right">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sites.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="font-medium">{s.name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {s.lat.toFixed(2)}°N, {s.lon.toFixed(2)}°E
                      </TableCell>
                      <TableCell className="text-right text-sm">{s.capacity_kw != null ? `${s.capacity_kw / 1000} MW` : "—"}</TableCell>
                      <TableCell className="text-right text-xs capitalize">{s.status.replace("_", " ")}</TableCell>
                    </TableRow>
                  ))}
                  {!sites.length && error == null && (
                    <TableRow>
                      <TableCell colSpan={4} className="text-sm text-muted-foreground">
                        Loading sites...
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Global solar models</CardTitle>
              <CardDescription>One per horizon, chosen with “Use for forecasts” on a finished solar run.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {HORIZONS.map((h) => {
                const m = models.find((x) => x.horizon === h)
                return (
                  <div key={h} className="rounded-md border border-border p-3 text-sm">
                    <p className="font-medium">{h} h ahead</p>
                    {m ? (
                      <p className="text-xs text-muted-foreground">
                        <span className="font-mono">{m.run_id}</span>, promoted {formatTimestamp(m.promoted_at)}
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">No model yet</p>
                    )}
                  </div>
                )
              })}
            </CardContent>
          </Card>
        </div>
      </section>
    </PageLayout>
  )
}
