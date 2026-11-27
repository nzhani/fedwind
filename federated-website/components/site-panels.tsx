"use client"

// Plant page building blocks (APP_PAGES_SPEC.md §2.3) shared with the admin pages:
// site kit, connection, forecast preview, activity, consents and the admin's decisions.

import { useEffect, useMemo, useState, type ReactNode } from "react"
import { Check, Copy, Download, Minus } from "lucide-react"
import { Card, DefList } from "@/components/fw/surface"
import { Pill, TextAction } from "@/components/fw/button"
import { ConfirmWithReason, Notice, Skeleton, toast } from "@/components/fw/feedback"
import { Switch } from "@/components/fw/form"
import { StatusPill } from "@/components/fw/status"
import { fmtDate, fmtDateTime, fmtPct, fmtPower, relTime } from "@/components/fw/format"
import { cn } from "@/lib/utils"
import {
  DATA_SOURCES,
  decideSite,
  downloadKit,
  leaveFederation,
  updateConsents,
  type ConsentUpdate,
  getForecast,
  listModels,
  pointPower,
  reissueKit,
  type ForecastResponse,
  type QualityDay,
  type SiteAction,
  type SiteDetail,
} from "@/lib/platform-api"

// -- kit ------------------------------------------------------------------------------------------

function CodeLine({ children }: { children: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="mt-2 flex items-center gap-2 rounded-[10px] bg-surface py-1.5 pl-3.5 pr-1.5">
      <code className="fw-num min-w-0 flex-1 overflow-x-auto whitespace-nowrap text-[13px] leading-6 text-ink">{children}</code>
      <button
        type="button"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(children)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          } catch {
            toast.error("Couldn't copy; select the text instead")
          }
        }}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-fw-muted hover:bg-white hover:text-ink"
        aria-label={copied ? "Copied" : "Copy command"}
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  )
}

function Steps({ children }: { children: ReactNode[] }) {
  return (
    <ol className="space-y-5">
      {children.map((c, i) => (
        <li key={i} className="flex gap-4">
          <span className="fw-num flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink text-xs text-white">{i + 1}</span>
          <div className="min-w-0 flex-1 pt-0.5 text-[15px] leading-6">{c}</div>
        </li>
      ))}
    </ol>
  )
}

export function KitCard({ site, onDownloaded }: { site: SiteDetail; onDownloaded: () => void }) {
  const [busy, setBusy] = useState(false)
  const file = `fedwind-site-${site.id}.zip`
  const expires = site.kit?.token_expires_at
  return (
    <Card
      label="Next step"
      title="Install the site kit"
      action={
        expires ? (
          <span className="fw-num text-xs text-fw-muted" title={`Valid until ${fmtDateTime(expires)}`}>
            key valid {relTime(expires).replace("in ", "")}
          </span>
        ) : undefined
      }
    >
      <p className="max-w-[560px] text-[15px] leading-6 text-fw-muted">
        The kit is a small container that connects this plant to ArqauQuat with a one-time key. Each download creates a new key and
        cancels the previous one.
      </p>
      <Pill
        className="mt-5"
        icon={<Download className="h-4 w-4" />}
        loading={busy}
        onClick={async () => {
          setBusy(true)
          try {
            const { blob, filename } = await downloadKit(site.id)
            const url = URL.createObjectURL(blob)
            const a = document.createElement("a")
            a.href = url
            a.download = filename
            document.body.appendChild(a)
            a.click()
            a.remove()
            setTimeout(() => URL.revokeObjectURL(url), 1000)
            toast.success("Kit downloaded. Install it within 72 hours.")
            onDownloaded()
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Download failed")
          } finally {
            setBusy(false)
          }
        }}
      >
        Download kit (.zip)
      </Pill>
      <div className="mt-8">
        <Steps>
          {[
            <div key="1">
              Copy the kit to the plant&apos;s computer and unpack it
              <CodeLine>{`unzip ${file} && cd fedwind-site-${site.id}`}</CodeLine>
            </div>,
            <div key="2">
              Start it (needs Docker)
              <CodeLine>docker compose up -d</CodeLine>
            </div>,
            <div key="3">This page turns Online within a minute.</div>,
          ]}
        </Steps>
      </div>
      <div className="mt-8 rounded-[12px] border border-dashed border-[rgba(34,34,34,0.25)] p-4">
        <span className="fw-label">Demo</span>
        <p className="mt-2 text-sm text-fw-muted">Simulate the plant on this computer: the same kit, with NASA POWER weather as its measurements.</p>
        <CodeLine>{`deploy/sim/run_site.sh ~/Downloads/${file}`}</CodeLine>
      </div>
      <p className="mt-5 text-sm text-fw-muted">Lost the kit after installing it? Ask an ArqauQuat admin to re-issue it.</p>
    </Card>
  )
}

// -- connection -----------------------------------------------------------------------------------

function QualityBars({ days }: { days: QualityDay[] }) {
  if (!days.length) return <p className="text-sm text-fw-muted">No daily report yet.</p>
  const max = 24
  return (
    <div>
      <div className="flex h-16 items-end gap-2" role="img" aria-label="Clean hours per day, last 7 days">
        {days.map((d, i) => {
          const clean = Math.max(0, d.rows - d.flagged)
          const h = Math.max(4, Math.round((clean / max) * 64))
          return (
            <div
              key={d.day}
              title={`${fmtDate(d.day)}: ${d.rows} rows, ${d.gaps} gaps, ${d.flagged} flagged, ${d.curtailed} curtailed`}
              className={cn("flex-1 rounded-[3px]", i === days.length - 1 ? "bg-ink" : "bg-[#cfcfcc]")}
              style={{ height: h }}
            />
          )
        })}
      </div>
      <div className="mt-2 flex gap-2">
        {days.map((d) => (
          <div key={d.day} className="fw-num flex-1 text-center text-[11px] text-fw-muted">
            {new Date(d.day).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ConnectionCard({ site, now }: { site: SiteDetail; now: number }) {
  const c = site.connection
  if (!c) return null
  const offline = c.state === "offline"
  return (
    <Card
      title="Connection"
      action={
        c.agent_version ? (
          <span className="fw-num text-xs text-fw-muted">
            agent {c.agent_version}
          </span>
        ) : undefined
      }
    >
      {c.update_available && (
        <Notice title={`Site kit ${c.update_available} is available`} className="mb-5">
          In the kit folder on the plant&apos;s server run <span className="fw-num">docker compose pull &amp;&amp; docker compose up -d</span>.
          The plant keeps its keys and data.
        </Notice>
      )}
      {offline && (
        <Notice tone="warn" title={`No heartbeat for ${relTime(c.last_heartbeat_at, now).replace(" ago", "")}`} className="mb-5">
          Check that the plant&apos;s computer is on and can reach ArqauQuat. Nothing is lost: the plant keeps its data.
        </Notice>
      )}
      {c.state === "never" ? (
        <p className="text-[15px] text-fw-muted">The kit hasn&apos;t reported yet.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
            <Mini label="Last heartbeat" value={relTime(c.last_heartbeat_at, now)} />
            <Mini label="Data until" value={c.last_data_hour ? fmtDateTime(c.last_data_hour, { utc: true }) : "—"} />
            <Mini label="Rows today" value={c.rows_today ?? "—"} hint={c.gaps_today != null ? `${c.gaps_today} gaps` : undefined} />
            <Mini label="Reports every" value={`${c.heartbeat_s} s`} />
          </div>
          <div className="mt-7">
            <div className="fw-label mb-3">Data quality, last 7 days</div>
            <QualityBars days={(c.quality_7d ?? []) as QualityDay[]} />
          </div>
          <p className="mt-5 text-sm text-fw-muted">Only counts arrive here. The plant&apos;s measurements stay at the plant.</p>
        </>
      )}
    </Card>
  )
}

function Mini({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="min-w-0">
      <div className="fw-label">{label}</div>
      <div className="fw-num mt-1 truncate text-[15px] text-ink">{value}</div>
      {hint && <div className="text-xs text-fw-muted">{hint}</div>}
    </div>
  )
}

// -- forecast preview -----------------------------------------------------------------------------

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null
  const w = 600
  const h = 90
  const max = Math.max(...values, 1e-9)
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - (v / max) * (h - 6) - 3])
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ")
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-[90px] w-full" aria-hidden>
      <path d={`${line} L${w} ${h} L0 ${h} Z`} fill="rgba(255,63,16,0.1)" />
      <path d={line} fill="none" stroke="#ff3f10" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export function ForecastPreview({ site }: { site: SiteDetail }) {
  const [data, setData] = useState<ForecastResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [horizon, setHorizon] = useState<number | null>(null)
  const consented = Boolean((site.consents as Record<string, unknown>)?.share_forecast_window) || site.kind !== "plant"

  useEffect(() => {
    if (!consented || site.status !== "active") return
    let cancelled = false
    ;(async () => {
      try {
        const models = (await listModels()).filter((m) => m.energy_type === site.energy_type)
        if (!models.length) throw new Error(`No ${site.energy_type} model serves forecasts yet.`)
        const h = models.some((m) => m.horizon === 72) ? 72 : Math.min(...models.map((m) => m.horizon))
        const f = await getForecast({ energyType: site.energy_type, site: site.id, horizon: h })
        if (!cancelled) {
          setHorizon(h)
          setData(f)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [site.id, site.energy_type, site.status, consented, site.connection?.last_data_hour])

  const values = useMemo(() => {
    if (!data) return []
    const series = data.forecast.length > 2 ? data.forecast : [...data.actual.slice(-24), ...data.forecast]
    return series.map((p) => pointPower(p, data.energy_type) ?? 0)
  }, [data])

  if (site.status !== "active") return null
  const href = `/forecast?energy=${site.energy_type}&site=${encodeURIComponent(site.id)}${horizon ? `&horizon=${horizon}` : ""}`
  const next = data?.forecast[0]

  return (
    <Card title="Forecast" action={consented && <TextAction href={href}>Open forecast</TextAction>}>
      {!consented ? (
        <p className="text-[15px] leading-6 text-fw-muted">
          Central forecasting is off for this plant, so the server has no recent data to forecast from. Forecasts on the plant&apos;s own
          computer come with a later milestone (M7).
        </p>
      ) : error ? (
        <p className="text-[15px] text-fw-muted">{error}</p>
      ) : !data ? (
        <Skeleton className="h-[130px] w-full" />
      ) : (
        <>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <div>
              <span className="fw-num text-[32px] leading-[38px] tracking-[-0.01em]">{fmtPower(next ? pointPower(next, data.energy_type) : null)}</span>
              <span className="ml-2 text-sm text-fw-muted">next hour · {fmtPct(next?.capacity_factor)} of {fmtPower(data.capacity_kw)}</span>
            </div>
          </div>
          <div className="mt-4">
            <Sparkline values={values} />
          </div>
          <p className="mt-3 text-sm text-fw-muted">
            {data.forecast.length > 2 ? `Next ${horizon} h` : "Last 24 h and the next hour"} from the shared model{" "}
            <span className="fw-num text-ink">{data.model.run_id}</span>, promoted {relTime(data.model.promoted_at)}.
          </p>
        </>
      )}
    </Card>
  )
}

// -- activity and consents ------------------------------------------------------------------------

const ACTIVITY: Record<string, string> = {
  register: "Registered",
  import: "Imported",
  edit: "Details edited",
  approve: "Approved",
  reject: "Rejected",
  kit: "Kit downloaded",
  enroll: "Kit installed",
  enroll_failed: "Kit refused (used or expired key)",
  online: "Online",
  suspend: "Suspended",
  resume: "Resumed",
  revoke: "Revoked",
  reissue: "Kit re-issued",
}

export function ActivityCard({ site, now }: { site: SiteDetail; now: number }) {
  const items = [...site.history].reverse()
  return (
    <Card title="Activity">
      {items.length === 0 ? (
        <p className="text-sm text-fw-muted">Nothing yet.</p>
      ) : (
        <ol className="relative space-y-4 before:absolute before:bottom-2 before:left-[3px] before:top-2 before:w-px before:bg-line">
          {items.map((h, i) => (
            <li key={`${h.at}-${i}`} className="relative pl-5">
              <span className={cn("absolute left-0 top-[7px] h-[7px] w-[7px] rounded-full", i === 0 ? "bg-fw-accent" : "bg-ink")} aria-hidden />
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-medium text-ink">{ACTIVITY[h.action] ?? h.action}</span>
                <span className="fw-num shrink-0 text-xs text-fw-muted" title={fmtDateTime(h.at)}>
                  {relTime(h.at, now)}
                </span>
              </div>
              {(h.actor || h.note) && (
                <div className="mt-0.5 text-sm text-fw-muted">
                  {h.actor}
                  {h.actor && h.note ? " · " : ""}
                  {h.note && <span className="text-ink">&ldquo;{h.note}&rdquo;</span>}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}

const CONSENT_ROWS: { key: keyof ConsentUpdate; label: string; on: string; off: string }[] = [
  { key: "train", label: "Federated training", on: "Joins training runs", off: "Paused: joins no training run" },
  { key: "share_forecast_window", label: "Central forecasting", on: "Shares the last 14 days of one variable",
    off: "Shares nothing; forecasts at the plant" },
  { key: "public_forecasts", label: "Public forecasts", on: "Visitors see this plant's forecasts", off: "Private" },
]

/** Consents; the plant's operators (and admins) change them here while the plant takes part. */
export function ConsentsCard({ site, editable = false, onChanged }: {
  site: SiteDetail
  editable?: boolean
  onChanged?: (s: SiteDetail) => void
}) {
  const c = (site.consents ?? {}) as Record<string, unknown>
  const [busy, setBusy] = useState<string | null>(null)
  const [leaving, setLeaving] = useState(false)
  const canChange = editable && ["approved", "active", "suspended"].includes(site.status)

  const toggle = async (key: keyof ConsentUpdate, value: boolean) => {
    if (key === "share_forecast_window" && !value &&
        !window.confirm("Stop sharing? The windows already shared are deleted and central forecasts stop.")) return
    setBusy(key)
    try {
      const next = { train: Boolean(c.train), share_forecast_window: Boolean(c.share_forecast_window),
                     public_forecasts: Boolean(c.public_forecasts), [key]: value }
      onChanged?.(await updateConsents(site.id, next))
      toast.success(key === "train" ? (value ? "Training resumed" : "Training paused") : "Consent updated")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update the consent")
    } finally {
      setBusy(null)
    }
  }

  const leave = async (reason: string) => {
    setBusy("leave")
    try {
      onChanged?.(await leaveFederation(site.id, reason))
      toast.success("The plant has left the federation")
      setLeaving(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not leave")
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card title={canChange ? "Participation" : "Consents"}>
      <ul className="space-y-3">
        {CONSENT_ROWS.map((r) => {
          const on = Boolean(c[r.key])
          return (
            <li key={r.key} className="flex items-center justify-between gap-3 text-sm">
              <div className="min-w-0">
                <div className={on ? "text-ink" : "text-fw-muted"}>{r.label}</div>
                {canChange && <div className="text-xs text-fw-muted">{on ? r.on : r.off}</div>}
              </div>
              {canChange ? (
                <Switch checked={on} disabled={busy !== null} label={r.label} onChange={(v) => toggle(r.key, v)} />
              ) : on ? (
                <Check className="h-4 w-4 text-ink" aria-label="yes" />
              ) : (
                <Minus className="h-4 w-4 text-fw-muted" aria-label="no" />
              )}
            </li>
          )
        })}
      </ul>
      {canChange && (
        <div className="mt-5 border-t border-line pt-4">
          {leaving ? (
            <ConfirmWithReason action="Leave for good" busy={busy === "leave"} placeholder="Why the plant leaves"
              onCancel={() => setLeaving(false)} onConfirm={leave} />
          ) : (
            <TextAction onClick={() => setLeaving(true)}>Leave the federation</TextAction>
          )}
          <p className="mt-2 text-xs text-fw-muted">
            Final: the plant&apos;s certificate and Flower node stop working. To pause, switch training off instead.
          </p>
        </div>
      )}
    </Card>
  )
}

export function DetailsCard({ site }: { site: SiteDetail }) {
  const eq = (site.equipment ?? {}) as Record<string, unknown>
  const items: { label: string; value: ReactNode; mono?: boolean }[] = [
    { label: "Site id", value: site.id, mono: true },
    { label: "Organization", value: site.org_name ?? (site.kind === "plant" ? "—" : "ArqauQuat lab") },
    { label: "Coordinates", value: `${site.lat.toFixed(4)}, ${site.lon.toFixed(4)}`, mono: true },
    { label: "Time zone", value: site.timezone },
    { label: "Capacity", value: fmtPower(site.capacity_kw), mono: true },
  ]
  if (site.energy_type === "wind" && eq.turbine_model) {
    items.push(
      { label: "Turbines", value: `${eq.turbine_count} × ${eq.turbine_model}` },
      { label: "Rated power", value: eq.rated_power_kw ? `${eq.rated_power_kw} kW each` : "—", mono: true },
      { label: "Hub height", value: eq.hub_height_m ? `${eq.hub_height_m} m` : "—", mono: true },
    )
  }
  if (site.energy_type === "solar" && eq.module_type) {
    items.push(
      { label: "Modules", value: String(eq.module_type) },
      { label: "Mounting", value: String(eq.tracking ?? "fixed") },
      { label: "Tilt / azimuth", value: `${eq.tilt_deg}° / ${eq.azimuth_deg}°`, mono: true },
    )
  }
  if (site.data_source) items.push({ label: "Data source", value: DATA_SOURCES.find((d) => d.value === site.data_source)?.label ?? site.data_source })
  if (site.contact) items.push({ label: "Technical contact", value: site.contact })
  return (
    <Card title="Details" bodyClassName="pt-2">
      <DefList items={items} />
    </Card>
  )
}

// -- the admin's decisions ------------------------------------------------------------------------

type AdminAction = SiteAction | "reissue"

const ADMIN_ACTIONS: Record<string, AdminAction[]> = {
  registered: ["approve", "reject"],
  approved: ["revoke"],
  active: ["suspend", "reissue", "revoke"],
  suspended: ["resume", "reissue", "revoke"],
}
const LABEL: Record<AdminAction, string> = {
  approve: "Approve",
  reject: "Reject",
  suspend: "Suspend",
  resume: "Resume",
  revoke: "Revoke",
  reissue: "Re-issue kit",
}
const NEEDS_REASON: AdminAction[] = ["reject", "suspend", "revoke", "reissue"]
const DONE: Record<AdminAction, string> = {
  approve: "Approved. The operator can download the kit.",
  reject: "Rejected. The operator sees your reason.",
  suspend: "Suspended. The plant learns it on its next heartbeat.",
  resume: "Resumed.",
  revoke: "Revoked. The plant's key no longer works.",
  reissue: "Credentials revoked. The operator can download a new kit.",
}

export function adminActionsFor(site: Pick<SiteDetail, "status" | "kind">): AdminAction[] {
  if (site.kind !== "plant") return []
  return ADMIN_ACTIONS[site.status] ?? []
}

export function SiteAdminActions({
  site,
  onChanged,
  compact,
}: {
  site: SiteDetail
  onChanged: (s: SiteDetail) => void
  compact?: boolean
}) {
  const [pending, setPending] = useState<AdminAction | null>(null)
  const [busy, setBusy] = useState(false)
  const actions = adminActionsFor(site)
  if (!actions.length) return compact ? null : <p className="text-sm text-fw-muted">No decisions to take in this state.</p>

  const run = async (action: AdminAction, note?: string) => {
    setBusy(true)
    try {
      const updated = action === "reissue" ? await reissueKit(site.id, note ?? "") : await decideSite(site.id, action, note)
      toast.success(`${site.name}: ${DONE[action]}`)
      setPending(null)
      onChanged(updated)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (pending) {
    return <ConfirmWithReason action={LABEL[pending]} busy={busy} onCancel={() => setPending(null)} onConfirm={(r) => run(pending, r)} />
  }
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map((a) => (
        <Pill
          key={a}
          size="s"
          variant={a === "approve" || a === "resume" ? "primary" : a === "revoke" || a === "reject" ? "danger" : "outline"}
          disabled={busy}
          loading={busy && !NEEDS_REASON.includes(a)}
          onClick={() => (NEEDS_REASON.includes(a) ? setPending(a) : run(a))}
        >
          {LABEL[a]}
        </Pill>
      ))}
    </div>
  )
}

export function StatusNotice({ site }: { site: SiteDetail }) {
  const note = site.decision_note
  const when = site.decided_at ? fmtDate(site.decided_at) : null
  if (site.status === "registered")
    return <Notice title="Waiting for approval">An ArqauQuat admin checks the details. You can still edit them until then.</Notice>
  if (site.status === "suspended")
    return (
      <Notice tone="warn" title={`Suspended by the ArqauQuat team${when ? ` on ${when}` : ""}`}>
        {note ? `“${note}”. ` : ""}The plant sits out training and forecasts until it is resumed; the kit keeps running.
      </Notice>
    )
  if (site.status === "rejected")
    return (
      <Notice tone="error" title={`Rejected${when ? ` on ${when}` : ""}`}>
        {note ? `“${note}”. ` : ""}Register again with corrected details.
      </Notice>
    )
  if (site.status === "revoked")
    return (
      <Notice tone="error" title={`Revoked${when ? ` on ${when}` : ""}`}>
        {note ? `“${note}”. ` : ""}The plant is no longer part of the federation.
      </Notice>
    )
  return null
}

export { StatusPill }
