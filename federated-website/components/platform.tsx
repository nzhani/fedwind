"use client"

// Shared pieces for the Forecast, Training and Experiments pages.

import { ReactNode } from "react"
import { AlertCircle, PlugZap } from "lucide-react"
import { SectionHeader } from "@/components/section-header"
import { cn } from "@/lib/utils"
import { PlatformApiError, type RunStatus } from "@/lib/platform-api"

export function PageHeader({ badge, title, description }: { badge: string; title: string; description: string }) {
  return (
    <section className="bg-gradient-to-b from-primary/5 to-background">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          <SectionHeader badge={badge} title={title} description={description} centered />
        </div>
      </div>
    </section>
  )
}

/** 503 from the API: it works, but the federation or inference isn't connected yet. */
export function NotConnectedNotice({ title, message, children }: { title: string; message: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 flex items-start gap-3">
      <PlugZap className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
      <div className="space-y-1">
        <h4 className="font-semibold text-amber-900">{title}</h4>
        <p className="text-sm text-amber-800">{message}</p>
        {children}
      </div>
    </div>
  )
}

export function ErrorNotice({ title = "Error", message }: { title?: string; message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex items-start gap-3">
      <AlertCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
      <div>
        <h4 className="font-semibold text-red-800">{title}</h4>
        <p className="text-sm text-red-700">{message}</p>
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

const STATUS_STYLES: Record<RunStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  running: "bg-blue-100 text-blue-700",
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  stopped: "bg-amber-100 text-amber-800",
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", STATUS_STYLES[status])}>
      {status === "running" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-600" />}
      {status}
    </span>
  )
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
