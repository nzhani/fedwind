"use client"

// Shared pieces for the Forecast, Training and Experiments pages.

import { ReactNode } from "react"
import { AlertCircle, PlugZap } from "lucide-react"
import { RunPill } from "@/components/fw/status"
import { PlatformApiError, type RunStatus } from "@/lib/platform-api"

export function PageHeader({ badge, title, description }: { badge: string; title: string; description: string }) {
  return (
    <section className="mx-auto max-w-[1280px] px-5 pb-10 pt-8 sm:px-10">
      <div className="fw-label mb-3">{badge}</div>
      <h1 className="fw-page-title max-w-[900px] text-ink">{title}</h1>
      {description && <p className="mt-3 max-w-[680px] text-base leading-6 text-fw-muted">{description}</p>}
    </section>
  )
}

/** 503 from the API: it works, but the federation or inference isn't connected yet. */
export function NotConnectedNotice({ title, message, children }: { title: string; message: string; children?: ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-[12px] bg-paper-warm px-4 py-3 text-sm">
      <PlugZap className="mt-0.5 h-4 w-4 shrink-0 text-ink" />
      <div className="space-y-1">
        <h4 className="font-medium text-ink">{title}</h4>
        <p className="text-fw-muted">{message}</p>
        {children}
      </div>
    </div>
  )
}

export function ErrorNotice({ title = "Error", message }: { title?: string; message: string }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-[12px] bg-fw-accent-soft px-4 py-3 text-sm">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-fw-accent-dark" />
      <div>
        <h4 className="font-medium text-ink">{title}</h4>
        <p className="break-words text-fw-muted">{message}</p>
      </div>
    </div>
  )
}

/** Picks the right notice for an API error. */
export function ApiErrorNotice({ error, notConnectedTitle }: { error: unknown; notConnectedTitle: string }) {
  if (error instanceof PlatformApiError && error.notConnected) {
    return <NotConnectedNotice title={notConnectedTitle} message={error.message} />
  }
  if (error instanceof PlatformApiError && error.status === 0) {
    return <ErrorNotice title="API unreachable" message={error.message} />
  }
  return <ErrorNotice message={error instanceof Error ? error.message : String(error)} />
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return <RunPill status={status} />
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—"
  if (seconds < 60) return `${seconds.toFixed(0)} s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m < 60 ? `${m} min ${s} s` : `${Math.floor(m / 60)} h ${m % 60} min`
}
