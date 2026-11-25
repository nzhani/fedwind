// One status pill everywhere (APP_PAGES_SPEC.md §1.6): ink text on a soft fill, colour only in the dot.

import type { ReactNode } from "react"
import { Sun, Wind } from "lucide-react"
import { cn } from "@/lib/utils"
import type { EnergyType, RunStatus, SiteDetail, SiteStatus } from "@/lib/platform-api"

export type Tone = "ok" | "warn" | "info" | "off" | "danger" | "accent" | "none"

const DOT: Record<Tone, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  info: "bg-info",
  off: "bg-off",
  danger: "bg-fw-accent-dark",
  accent: "bg-fw-accent",
  none: "",
}

export function StatusPill({ tone, children, pulse, className, title }: { tone: Tone; children: ReactNode; pulse?: boolean; className?: string; title?: string }) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-[22px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-surface px-2.5 text-xs font-medium leading-4 text-ink",
        className,
      )}
    >
      {tone !== "none" && (
        <span className="relative flex h-1.5 w-1.5">
          {pulse && <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", DOT[tone])} />}
          <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", DOT[tone])} />
        </span>
      )}
      {children}
    </span>
  )
}

/** What a site's state means for people (status + live connection). */
export function siteState(site: Pick<SiteDetail, "status" | "kind"> & Partial<Pick<SiteDetail, "connection" | "kit">>): { tone: Tone; label: string } {
  const s: SiteStatus = site.status
  if (s === "registered") return { tone: "warn", label: "Waiting for approval" }
  if (s === "approved") return { tone: "info", label: site.kit?.token_expires_at ? "Kit issued" : "Approved" }
  if (s === "active") {
    if (site.kind !== "plant" || site.connection?.state === "lab") return { tone: "ok", label: "Lab site" }
    if (site.connection?.state === "online") return { tone: "ok", label: "Online" }
    if (site.connection?.state === "offline") return { tone: "off", label: "Offline" }
    return { tone: "info", label: "Connecting" }
  }
  if (s === "suspended") return { tone: "off", label: "Suspended" }
  if (s === "rejected") return { tone: "danger", label: "Rejected" }
  if (s === "revoked") return { tone: "danger", label: "Revoked" }
  return { tone: "off", label: s.replace(/_/g, " ") }
}

export function SitePill({ site }: { site: Parameters<typeof siteState>[0] }) {
  const { tone, label } = siteState(site)
  return (
    <StatusPill tone={tone} pulse={label === "Online"}>
      {label}
    </StatusPill>
  )
}

const RUN: Record<RunStatus, { tone: Tone; label: string }> = {
  queued: { tone: "off", label: "Queued" },
  running: { tone: "info", label: "Running" },
  done: { tone: "ok", label: "Done" },
  failed: { tone: "danger", label: "Failed" },
  stopped: { tone: "warn", label: "Stopped" },
}

export function RunPill({ status }: { status: RunStatus }) {
  const r = RUN[status] ?? { tone: "off" as Tone, label: status }
  return (
    <StatusPill tone={r.tone} pulse={status === "running"}>
      {r.label}
    </StatusPill>
  )
}

export function EnergyIcon({ type, className }: { type: EnergyType; className?: string }) {
  const Icon = type === "solar" ? Sun : Wind
  return <Icon className={cn("h-5 w-5 text-ink", className)} strokeWidth={1.5} aria-label={type === "solar" ? "Solar" : "Wind"} />
}
