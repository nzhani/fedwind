"use client"

// Health (SITE_NETWORK_PLAN.md M8): one list of checks; refreshes every minute.

import { useCallback, useEffect, useState } from "react"
import { Card } from "@/components/fw/surface"
import { Pill } from "@/components/fw/button"
import { ApiError, SkeletonRows } from "@/components/fw/feedback"
import { StatusPill } from "@/components/fw/status"
import { relTime } from "@/components/fw/format"
import { getHealthReport, type HealthReport } from "@/lib/platform-api"

const TONE = { ok: "ok", warn: "warn", error: "danger" } as const
const LABEL = { ok: "OK", warn: "Check", error: "Problem" } as const

export default function HealthPage() {
  const [report, setReport] = useState<HealthReport | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    try {
      setReport(await getHealthReport())
      setError(null)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 60_000)
    return () => clearInterval(t)
  }, [load])

  if (error) return <ApiError error={error} onRetry={load} />
  if (!report) return <SkeletonRows rows={8} />
  const order = { error: 0, warn: 1, ok: 2 }
  const checks = [...report.checks].sort((a, b) => order[a.status] - order[b.status])

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <StatusPill tone={TONE[report.status]}>{LABEL[report.status]}</StatusPill>
          <span className="text-sm font-normal text-fw-muted">checked {relTime(report.checked_at)}</span>
        </span>
      }
      action={
        <Pill size="s" variant="outline" loading={busy} onClick={load}>
          Check again
        </Pill>
      }
      bodyClassName="pt-2"
    >
      <ul className="divide-y divide-line">
        {checks.map((c) => (
          <li key={c.name} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:gap-4">
            <span className="w-56 shrink-0 font-medium">{c.name}</span>
            <span className="flex-1 text-sm text-fw-muted">{c.detail}</span>
            <StatusPill tone={TONE[c.status]}>{LABEL[c.status]}</StatusPill>
          </li>
        ))}
      </ul>
    </Card>
  )
}
