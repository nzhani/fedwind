"use client"

// Your plants (APP_PAGES_SPEC.md §2.1): stat tiles + one table with live connection.

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Factory } from "lucide-react"
import { AppPage, Card, PageHeader, StatRow, StatTile, Table, Td, Th, Tr } from "@/components/fw/surface"
import { PillLink } from "@/components/fw/button"
import { ApiError, EmptyState, Gate, SkeletonRows } from "@/components/fw/feedback"
import { EnergyIcon, SitePill } from "@/components/fw/status"
import { fmtDate, fmtPower, relTime } from "@/components/fw/format"
import { useAuth } from "@/lib/auth"
import { listMySites, type SiteDetail } from "@/lib/platform-api"

export default function SitesPage() {
  const { user, loading: authLoading, isAdmin } = useAuth()
  const router = useRouter()
  const [sites, setSites] = useState<SiteDetail[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    try {
      const all = await listMySites()
      setSites(all.filter((s) => s.kind === "plant"))
      setError(null)
      setNow(Date.now())
    } catch (e) {
      setError(e)
    }
  }, [])

  useEffect(() => {
    if (!user) return
    load()
    const t = setInterval(load, 10_000)
    return () => clearInterval(t)
  }, [user, load])

  if (authLoading) return <AppPage><SkeletonRows /></AppPage>
  if (!user) {
    return (
      <AppPage>
        <PageHeader label="Sites" title="Your plants" />
        <Gate title="Log in to see your plants" login next="/sites">
          Plant operators register their plants here and follow them from approval to online.
        </Gate>
      </AppPage>
    )
  }
  if (user.role === "viewer") {
    return (
      <AppPage>
        <PageHeader label="Sites" title="Your plants" />
        <Gate title="This page is for plant operators">Ask an ArqauQuat admin to give your account operator access.</Gate>
      </AppPage>
    )
  }

  const list = sites ?? []
  const count = (pred: (s: SiteDetail) => boolean) => list.filter(pred).length

  return (
    <AppPage>
      <PageHeader
        label="Sites"
        title={isAdmin ? "Plants" : "Your plants"}
        description={
          isAdmin
            ? "Every plant registered by an organization. Lab sites and decisions live in Admin."
            : `Plants of ${user.organization?.name ?? "your organization"} in the federation.`
        }
        actions={
          isAdmin ? (
            <PillLink href="/admin/approvals" variant="outline">
              Approvals
            </PillLink>
          ) : (
            <PillLink href="/sites/new" arrow>
              Register plant
            </PillLink>
          )
        }
      />

      <StatRow>
        <StatTile label="Plants" value={sites ? list.length : "—"} />
        <StatTile label="Active" value={sites ? count((s) => s.status === "active") : "—"} />
        <StatTile label="Waiting for approval" value={sites ? count((s) => s.status === "registered") : "—"} />
        <StatTile label="Online now" value={sites ? count((s) => s.connection?.state === "online") : "—"} />
      </StatRow>

      {error ? <ApiError error={error} onRetry={load} className="mb-6" /> : null}

      <Card bodyClassName="pt-2">
        {!sites ? (
          <div className="pt-4">
            <SkeletonRows />
          </div>
        ) : list.length === 0 ? (
          <EmptyState
            icon={<Factory />}
            title="No plants yet"
            action={!isAdmin && <PillLink href="/sites/new" arrow>Register plant</PillLink>}
          >
            Register your first plant; an admin approves it, then you install the site kit.
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Plant</Th>
                {isAdmin && <Th>Organization</Th>}
                <Th>Type</Th>
                <Th right>Capacity</Th>
                <Th>Status</Th>
                <Th>Last heartbeat</Th>
                <Th right>Registered</Th>
              </tr>
            </thead>
            <tbody>
              {list.map((s) => (
                <Tr key={s.id} onClick={() => router.push(`/sites/${s.id}`)}>
                  <Td>
                    <div className="flex items-center gap-3">
                      <EnergyIcon type={s.energy_type} />
                      <div className="min-w-0">
                        <a
                          href={`/sites/${s.id}`}
                          onClick={(e) => e.preventDefault()}
                          className="block max-w-[260px] truncate font-medium text-ink"
                          title={s.name}
                        >
                          {s.name}
                        </a>
                        <div className="fw-num max-w-[260px] truncate text-xs text-fw-muted">{s.id}</div>
                      </div>
                    </div>
                  </Td>
                  {isAdmin && <Td className="max-w-[180px] truncate text-fw-muted">{s.org_name ?? "—"}</Td>}
                  <Td className="capitalize">{s.energy_type}</Td>
                  <Td right mono>
                    {fmtPower(s.capacity_kw)}
                  </Td>
                  <Td>
                    <SitePill site={s} />
                  </Td>
                  <Td mono className="text-fw-muted">
                    {s.connection?.last_heartbeat_at ? relTime(s.connection.last_heartbeat_at, now) : "—"}
                  </Td>
                  <Td right mono className="text-fw-muted">
                    {fmtDate(s.created_at)}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </AppPage>
  )
}
