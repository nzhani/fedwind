"use client"

// Approvals queue (APP_PAGES_SPEC.md §3.3): list of waiting plants at the left, the selected
// registration as a read-only review sheet at the right, decisions at the bottom.

import { useCallback, useEffect, useMemo, useState } from "react"
import { ExternalLink, Inbox } from "lucide-react"
import { Card, DefList } from "@/components/fw/surface"
import { ApiError, EmptyState, SkeletonRows } from "@/components/fw/feedback"
import { EnergyIcon } from "@/components/fw/status"
import { fmtDateTime, fmtPower, relTime } from "@/components/fw/format"
import { ConsentsCard, SiteAdminActions } from "@/components/site-panels"
import { cn } from "@/lib/utils"
import { DATA_SOURCES, getMySite, listMySites, type SiteDetail } from "@/lib/platform-api"

export default function ApprovalsPage() {
  const [queue, setQueue] = useState<SiteDetail[] | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<SiteDetail | null>(null)
  const [error, setError] = useState<unknown>(null)

  const load = useCallback(async () => {
    try {
      const all = await listMySites()
      const waiting = all.filter((s) => s.kind === "plant" && s.status === "registered").sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))
      setQueue(waiting)
      setError(null)
      setSelectedId((cur) => (cur && waiting.some((s) => s.id === cur) ? cur : waiting[0]?.id ?? null))
    } catch (e) {
      setError(e)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 15_000)
    return () => clearInterval(t)
  }, [load])

  useEffect(() => {
    if (!selectedId) return setDetail(null)
    getMySite(selectedId).then(setDetail).catch(setError)
  }, [selectedId])

  const selected = useMemo(() => (detail?.id === selectedId ? detail : null), [detail, selectedId])

  if (error && !queue) return <ApiError error={error} onRetry={load} />
  if (!queue) return <SkeletonRows />
  if (queue.length === 0) {
    return (
      <Card>
        <EmptyState icon={<Inbox />} title="No plants waiting">
          New registrations appear here.
        </EmptyState>
      </Card>
    )
  }

  return (
    <div className="grid gap-6 lg:grid-cols-12">
      <Card className="self-start lg:col-span-5" bodyClassName="p-0">
        <ul className="divide-y divide-line">
          {queue.map((s) => {
            const on = s.id === selectedId
            return (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(s.id)}
                  aria-current={on}
                  className={cn(
                    "relative flex w-full items-center gap-4 px-6 py-4 text-left transition-colors first:rounded-t-[16px] last:rounded-b-[16px] hover:bg-paper-warm",
                    on && "bg-paper-warm before:absolute before:inset-y-3 before:left-0 before:w-0.5 before:rounded-full before:bg-ink",
                  )}
                >
                  <EnergyIcon type={s.energy_type} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium text-ink">{s.name}</div>
                    <div className="truncate text-sm text-fw-muted">
                      {s.org_name ?? "—"} · <span className="fw-num">{fmtPower(s.capacity_kw)}</span>
                    </div>
                  </div>
                  <span className="fw-num shrink-0 text-xs text-fw-muted">{relTime(s.created_at)}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </Card>

      <div className="space-y-6 lg:col-span-7">
        {!selected ? (
          <Card>
            <SkeletonRows />
          </Card>
        ) : (
          <Review site={selected} onDecided={load} />
        )}
      </div>
    </div>
  )
}

function Review({ site, onDecided }: { site: SiteDetail; onDecided: () => void }) {
  const eq = (site.equipment ?? {}) as Record<string, unknown>
  const submitted = site.history.find((h) => h.action === "register")
  return (
    <>
      <Card
        label={`${site.energy_type === "wind" ? "Wind" : "Solar"} plant · waiting ${relTime(site.created_at).replace(" ago", "")}`}
        title={<span className="text-xl">{site.name}</span>}
        bodyClassName="pt-2"
      >
        <DefList
          items={[
            { label: "Organization", value: site.org_name },
            { label: "Submitted", value: `${fmtDateTime(site.created_at)}${submitted?.actor ? ` by ${submitted.actor}` : ""}` },
            {
              label: "Coordinates",
              value: (
                <a
                  className="inline-flex items-center gap-1 underline-offset-4 hover:underline"
                  href={`https://www.openstreetmap.org/?mlat=${site.lat}&mlon=${site.lon}#map=11/${site.lat}/${site.lon}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {site.lat.toFixed(4)}, {site.lon.toFixed(4)}
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                </a>
              ),
              mono: true,
            },
            { label: "Time zone", value: site.timezone },
            { label: "Capacity", value: fmtPower(site.capacity_kw), mono: true },
            ...(site.energy_type === "wind"
              ? [
                  { label: "Turbines", value: `${eq.turbine_count ?? "?"} × ${eq.turbine_model ?? "?"}` },
                  { label: "Rated / hub height", value: `${eq.rated_power_kw ?? "—"} kW · ${eq.hub_height_m ?? "—"} m`, mono: true },
                ]
              : [
                  { label: "Modules", value: String(eq.module_type ?? "—") },
                  { label: "Mounting · tilt · azimuth", value: `${eq.tracking ?? "fixed"} · ${eq.tilt_deg}° · ${eq.azimuth_deg}°` },
                ]),
            { label: "Data source", value: DATA_SOURCES.find((d) => d.value === site.data_source)?.label ?? site.data_source },
            { label: "Technical contact", value: site.contact },
          ]}
        />
      </Card>
      <div className="rounded-[16px] border border-line bg-white p-4">
        <SiteAdminActions site={site} onChanged={onDecided} />
      </div>
      <ConsentsCard site={site} />
    </>
  )
}
