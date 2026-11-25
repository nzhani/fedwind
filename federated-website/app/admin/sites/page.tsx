"use client"

// All sites (APP_PAGES_SPEC.md §3.4): filters, one table, a ⋯ menu per plant.

import { Fragment, useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { MoreHorizontal, Search } from "lucide-react"
import { Card, Table, Td, Th, Tr } from "@/components/fw/surface"
import { Input, Segmented, Select } from "@/components/fw/form"
import { ApiError, ConfirmWithReason, EmptyState, SkeletonRows, toast } from "@/components/fw/feedback"
import { EnergyIcon, SitePill, siteState } from "@/components/fw/status"
import { fmtPower, relTime } from "@/components/fw/format"
import { adminActionsFor } from "@/components/site-panels"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { decideSite, listMySites, reissueKit, type SiteAction, type SiteDetail } from "@/lib/platform-api"

type Pending = { site: SiteDetail; action: SiteAction | "reissue" }
const LABEL = { approve: "Approve", reject: "Reject", suspend: "Suspend", resume: "Resume", revoke: "Revoke", reissue: "Re-issue kit" } as const

export default function AdminSitesPage() {
  const router = useRouter()
  const [sites, setSites] = useState<SiteDetail[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [q, setQ] = useState("")
  const [type, setType] = useState<"all" | "wind" | "solar">("all")
  const [source, setSource] = useState<"all" | "plant" | "lab">("all")
  const [status, setStatus] = useState("all")
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    try {
      setSites(await listMySites())
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

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (sites ?? []).filter((s) => {
      if (type !== "all" && s.energy_type !== type) return false
      if (source === "plant" && s.kind !== "plant") return false
      if (source === "lab" && s.kind === "plant") return false
      if (status !== "all") {
        const label = siteState(s).label
        if (status === "online" ? label !== "Online" : status === "offline" ? label !== "Offline" : s.status !== status) return false
      }
      return !needle || [s.name, s.id, s.org_name ?? ""].some((v) => v.toLowerCase().includes(needle))
    })
  }, [sites, q, type, source, status])

  const run = async (p: Pending, note?: string) => {
    setBusy(true)
    try {
      if (p.action === "reissue") await reissueKit(p.site.id, note ?? "")
      else await decideSite(p.site.id, p.action, note)
      toast.success(`${p.site.name}: ${LABEL[p.action].toLowerCase()} done`)
      setPending(null)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative lg:w-[300px]">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fw-muted" aria-hidden />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, id or organization" className="pl-10" aria-label="Search sites" />
        </div>
        <Segmented ariaLabel="Type" value={type} onChange={setType} options={[{ value: "all", label: "All" }, { value: "wind", label: "Wind" }, { value: "solar", label: "Solar" }]} />
        <Segmented ariaLabel="Source" value={source} onChange={setSource} options={[{ value: "all", label: "All" }, { value: "plant", label: "Plants" }, { value: "lab", label: "Lab" }]} />
        <div className="lg:w-[220px]">
          <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="all">Any status</option>
            <option value="online">Online</option>
            <option value="offline">Offline</option>
            <option value="registered">Waiting for approval</option>
            <option value="approved">Approved</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="rejected">Rejected</option>
            <option value="revoked">Revoked</option>
          </Select>
        </div>
      </div>

      {error ? <ApiError error={error} onRetry={load} className="mb-6" /> : null}

      <Card bodyClassName="pt-2">
        {!sites ? (
          <div className="pt-4">
            <SkeletonRows />
          </div>
        ) : shown.length === 0 ? (
          <EmptyState title="No sites match">Clear a filter to see more.</EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Site</Th>
                <Th>Organization</Th>
                <Th right>Capacity</Th>
                <Th>Status</Th>
                <Th>Last heartbeat</Th>
                <Th className="w-12">
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {shown.map((s) => {
                const actions = adminActionsFor(s)
                return (
                  <Fragment key={s.id}>
                    <Tr onClick={() => router.push(`/sites/${s.id}`)}>
                      <Td>
                        <div className="flex items-center gap-3">
                          <EnergyIcon type={s.energy_type} />
                          <div className="min-w-0">
                            <div className="max-w-[240px] truncate font-medium" title={s.name}>
                              {s.name}
                            </div>
                            <div className="fw-num max-w-[240px] truncate text-xs text-fw-muted">{s.id}</div>
                          </div>
                        </div>
                      </Td>
                      <Td className="max-w-[200px] truncate text-fw-muted">{s.kind === "plant" ? s.org_name ?? "—" : "Lab site"}</Td>
                      <Td right mono>
                        {fmtPower(s.capacity_kw)}
                      </Td>
                      <Td>
                        <SitePill site={s} />
                      </Td>
                      <Td mono className="text-fw-muted">
                        {s.connection?.last_heartbeat_at ? relTime(s.connection.last_heartbeat_at, now) : "—"}
                      </Td>
                      <Td className="text-right" >
                        <div onClick={(e) => e.stopPropagation()}>
                          <DropdownMenu>
                            <DropdownMenuTrigger
                              className="flex h-8 w-8 items-center justify-center rounded-full text-fw-muted outline-none hover:bg-white hover:text-ink data-[state=open]:bg-white"
                              aria-label={`Actions for ${s.name}`}
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-48 rounded-[14px] border-line p-1.5 shadow-[0_12px_32px_rgba(34,34,34,0.12)]">
                              <DropdownMenuItem className="rounded-[10px] px-2.5 py-2" onSelect={() => router.push(`/sites/${s.id}`)}>
                                Open
                              </DropdownMenuItem>
                              {actions.length > 0 && <DropdownMenuSeparator />}
                              {actions.map((a) => (
                                <DropdownMenuItem
                                  key={a}
                                  className={`rounded-[10px] px-2.5 py-2 ${a === "revoke" || a === "reject" ? "text-fw-accent-dark focus:text-fw-accent-dark" : ""}`}
                                  onSelect={() => (a === "approve" || a === "resume" ? run({ site: s, action: a }) : setPending({ site: s, action: a }))}
                                >
                                  {LABEL[a]}
                                </DropdownMenuItem>
                              ))}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </Td>
                    </Tr>
                    {pending?.site.id === s.id && (
                      <tr className="border-b border-line bg-paper-warm">
                        <td colSpan={6} className="px-6 py-3">
                          <ConfirmWithReason action={LABEL[pending.action]} busy={busy} onCancel={() => setPending(null)} onConfirm={(r) => run(pending, r)} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  )
}
