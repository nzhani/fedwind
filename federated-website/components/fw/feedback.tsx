"use client"

// Feedback patterns (APP_PAGES_SPEC.md §1.8): notices, empty states, skeletons, confirm-with-reason,
// the progress stepper and the sign-in / role gate.

import { useState, type ReactNode } from "react"
import { AlertCircle, Info, PlugZap } from "lucide-react"
import { Toaster as Sonner, toast } from "sonner"
import { cn } from "@/lib/utils"
import { PlatformApiError } from "@/lib/platform-api"
import { Pill, PillLink } from "@/components/fw/button"
import { Input } from "@/components/fw/form"
import { Card } from "@/components/fw/surface"

export { toast }

export function Toaster() {
  return (
    <Sonner
      position="bottom-right"
      duration={4000}
      toastOptions={{
        classNames: {
          toast: "!rounded-[12px] !border !border-line !bg-white !text-ink !text-sm !shadow-[0_12px_32px_rgba(34,34,34,0.12)] !font-sans",
          description: "!text-fw-muted",
          actionButton: "!bg-ink !text-white !rounded-full",
        },
      }}
    />
  )
}

export function Notice({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: "info" | "error" | "warn"
  title?: ReactNode
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  const Icon = tone === "error" ? AlertCircle : tone === "warn" ? PlugZap : Info
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-[12px] px-4 py-3 text-sm leading-5 text-ink",
        tone === "error" ? "bg-fw-accent-soft" : "bg-paper-warm",
        className,
      )}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", tone === "error" ? "text-fw-accent-dark" : "text-ink")} aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <div className="font-medium">{title}</div>}
        {children && <div className={cn(title && "mt-0.5 text-fw-muted", "break-words")}>{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

/** Picks words for an API error: not connected (503), unreachable (0), or the API's message. */
export function ApiError({ error, notConnected = "Not connected yet", onRetry, className }: { error: unknown; notConnected?: string; onRetry?: () => void; className?: string }) {
  const retry = onRetry && (
    <button type="button" onClick={onRetry} className="text-sm font-medium text-ink underline underline-offset-4">
      Retry
    </button>
  )
  if (error instanceof PlatformApiError && error.status === 0) {
    return (
      <Notice tone="error" title="Can't reach ArqauQuat right now" action={retry} className={className}>
        {error.message}
      </Notice>
    )
  }
  if (error instanceof PlatformApiError && error.notConnected) {
    return (
      <Notice tone="warn" title={notConnected} action={retry} className={className}>
        {error.message}
      </Notice>
    )
  }
  return (
    <Notice tone="error" title="Something went wrong" action={retry} className={className}>
      {error instanceof Error ? error.message : String(error)}
    </Notice>
  )
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {icon && <div className="mb-4 text-fw-muted [&_svg]:h-6 [&_svg]:w-6 [&_svg]:stroke-[1.5]">{icon}</div>}
      <div className="text-xl font-medium text-ink">{title}</div>
      {children && <p className="mt-2 max-w-[440px] text-base leading-6 text-fw-muted">{children}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-skeleton", className)} aria-hidden />
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

/** The clicked action turns into a row: reason (required) + the destructive pill + Cancel. */
export function ConfirmWithReason({
  action,
  onConfirm,
  onCancel,
  placeholder = "Reason (the operator sees this)",
  busy,
}: {
  action: string
  onConfirm: (reason: string) => void
  onCancel: () => void
  placeholder?: string
  busy?: boolean
}) {
  const [reason, setReason] = useState("")
  return (
    <form
      className="flex w-full flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (reason.trim()) onConfirm(reason.trim())
      }}
    >
      <Input
        autoFocus
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder={placeholder}
        aria-label={`Reason to ${action.toLowerCase()}`}
        className="h-9 min-w-[220px] flex-1 text-sm"
        maxLength={1000}
      />
      <Pill type="submit" size="s" variant="danger" disabled={!reason.trim()} loading={busy}>
        {action}
      </Pill>
      <Pill size="s" variant="ghost" onClick={onCancel}>
        Cancel
      </Pill>
    </form>
  )
}

export interface Step {
  label: string
  at?: string | null
  done: boolean
  current?: boolean
}

/** Progress stepper (§2.3): dots on a hairline; done = ink, current = accent with a halo, future = hollow. */
export function Stepper({ steps, format }: { steps: Step[]; format: (iso: string) => string }) {
  return (
    <ol className="grid grid-cols-2 gap-y-6 sm:flex sm:items-start">
      {steps.map((s, i) => (
        <li key={s.label} className="relative flex-1">
          <div className="flex items-center">
            <span
              className={cn(
                "relative z-10 h-2.5 w-2.5 shrink-0 rounded-full",
                s.current ? "bg-fw-accent shadow-[0_0_0_5px_rgba(255,63,16,0.18)]" : s.done ? "bg-ink" : "border border-[#bdbdbd] bg-white",
              )}
              aria-hidden
            />
            {i < steps.length - 1 && <span className={cn("hidden h-px flex-1 sm:block", s.done && steps[i + 1].done ? "bg-ink" : "bg-line-strong")} />}
          </div>
          <div className={cn("mt-3 pr-4 text-sm font-medium", s.done || s.current ? "text-ink" : "text-fw-muted")}>
            {s.label}
            <span className="sr-only">{s.current ? " (current step)" : s.done ? " (done)" : " (not yet)"}</span>
          </div>
          <div className="fw-num mt-0.5 text-xs text-fw-muted">{s.at ? format(s.at) : s.current ? "waiting" : "—"}</div>
        </li>
      ))}
    </ol>
  )
}

/** Shown instead of a page when the visitor isn't signed in or has the wrong role (§4). */
export function Gate({ title, children, login, next }: { title: string; children?: ReactNode; login?: boolean; next?: string }) {
  return (
    <Card className="mx-auto max-w-[560px]">
      <EmptyState
        title={title}
        action={login ? <PillLink href={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`} arrow>Log in</PillLink> : undefined}
      >
        {children}
      </EmptyState>
    </Card>
  )
}
