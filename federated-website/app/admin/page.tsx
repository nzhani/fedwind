"use client"

// Admin overview (APP_PAGES_SPEC.md §3.2): tiles, needs attention, recent activity.

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { CheckCircle2 } from "lucide-react"
import { Card, StatRow, StatTile } from "@/components/fw/surface"
import { TextAction } from "@/components/fw/button"
import { ApiError, EmptyState, SkeletonRows } from "@/components/fw/feedback"
import { StatusPill } from "@/components/fw/status"
import { relTime } from "@/components/fw/format"
import { SECURITY_ACTIONS, sentence, targetHref } from "@/components/audit-line"
import { cn } from "@/lib/utils"
import { getAdminOverview, listMySites, type AdminOverview, type SiteDetail } from "@/lib/platform-api"
import { FederationMap } from "@/components/federation-map"

const ATTENTION_ACTION: Record<string, string> = { approval: "Review", offline: "Open", failed_run: "Open" }

export default function AdminOverviewPage() {
  const [data, setData] = useState<AdminOverview | null>(null)
  const [sites, setSites] = useState<SiteDetail[]>([])
  const [error, setError] = useState<unknown>(null)
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    try {
      const [o, s] = await Promise.all([getAdminOverview(), listMySites()])
      setData(o)
      setSites(s.filter((x) => x.status !== "rejected" && x.status !== "revoked"))
      setError(null)
      setNow(Date.now())
    } catch (e) {
      setError(e)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 10_000)
    return () => clearInterval(t)
  }, [load])

  const t = data?.tiles
  return (
    <div>
      {error ? <ApiError error={error} onRetry={load} className="mb-6" /> : null}
      <StatRow className="sm:grid-cols-5">
        <StatTile label="Waiting for approval" value={t ? t.waiting : "—"} />
        <StatTile label="Active sites" value={t ? t.active_sites : "—"} />
        <StatTile label="Online now" value={t ? t.online_now : "—"} hint="plants with a live kit" />
        <StatTile label="Users" value={t ? t.users : "—"} />
        <StatTile
          label="Training"
          value={t ? (t.run ? `${t.run.current_round}/${t.run.total_rounds}` : "Idle") : "—"}
          hint={t?.run ? <Link href={`/training/${t.run.run_id}`} className="underline-offset-4 hover:underline">{t.run.run_id}</Link> : "no run in progress"}
        />
      </StatRow>

      {sites.length > 0 && (
        <Card title="Federation map" className="mb-6" action={<span className="text-sm text-fw-muted">live, every 10 s</span>}>
          <FederationMap sites={sites} live hrefFor={(s) => `/sites/${encodeURIComponent(s.id)}`} className="mx-auto max-w-[980px]" />
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Needs attention" bodyClassName="pt-2">
          {!data ? (
            <div className="pt-2">
              <SkeletonRows rows={3} />
            </div>
          ) : data.attention.length === 0 ? (
            <EmptyState icon={<CheckCircle2 />} title="Nothing needs attention">
              New registrations, plants going offline and failed runs show up here.
            </EmptyState>
          ) : (
            <ul className="-mx-6 divide-y divide-line">
              {data.attention.map((a) => (
                <li key={`${a.kind}-${a.site_id ?? a.run_id}`}>
                  <Link
                    href={a.kind === "approval" ? "/admin/approvals" : a.link}
                    className="group flex items-center justify-between gap-4 px-6 py-4 transition-colors hover:bg-paper-warm"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <StatusPill tone={a.kind === "approval" ? "warn" : a.kind === "offline" ? "off" : "danger"}>
                        {a.kind === "approval" ? "Approval" : a.kind === "offline" ? "Offline" : "Failed run"}
                      </StatusPill>
                      <span className="truncate text-[15px] text-ink">{a.title}</span>
                    </div>
                    <span className="flex shrink-0 items-center gap-3 text-sm text-fw-muted">
                      <span className="fw-num hidden sm:inline">{relTime(a.since, now)}</span>
                      <span className="font-medium text-ink">{ATTENTION_ACTION[a.kind]} →</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recent activity" action={<TextAction href="/admin/audit">View all</TextAction>}>
          {!data ? (
            <SkeletonRows rows={5} />
          ) : (
            <ol className="relative space-y-3.5 before:absolute before:bottom-2 before:left-[3px] before:top-2 before:w-px before:bg-line">
              {data.recent.map((e) => {
                const s = sentence(e)
                const href = targetHref(e)
                return (
                  <li key={e.id} className="relative flex items-baseline justify-between gap-4 pl-5 text-sm">
                    <span className={cn("absolute left-0 top-[6px] h-[7px] w-[7px] rounded-full", SECURITY_ACTIONS.has(e.action) ? "bg-fw-accent-dark" : "bg-ink")} aria-hidden />
                    <span className="min-w-0 truncate text-fw-muted">
                      {s.actor && <span className="font-medium text-ink">{s.actor} </span>}
                      {s.verb}{" "}
                      {s.target &&
                        (href ? (
                          <Link href={href} className="fw-num text-ink underline-offset-4 hover:underline">
                            {s.target}
                          </Link>
                        ) : (
                          <span className="fw-num text-ink">{s.target}</span>
                        ))}
                    </span>
                    <span className="fw-num shrink-0 text-xs text-fw-muted">{relTime(e.at, now)}</span>
                  </li>
                )
              })}
            </ol>
          )}
        </Card>
      </div>
    </div>
  )
}
