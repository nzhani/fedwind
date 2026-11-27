"use client"

// Models (SITE_NETWORK_PLAN.md M7): every version per energy type and horizon, its gate report,
// promote any version (that is also the rollback), veto an automatic promotion within 24 h.

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { Check, X } from "lucide-react"
import { Card, Table, Td, Th, Tr } from "@/components/fw/surface"
import { Pill } from "@/components/fw/button"
import { ApiError, ConfirmWithReason, EmptyState, SkeletonRows, toast } from "@/components/fw/feedback"
import { EnergyIcon, StatusPill } from "@/components/fw/status"
import { fmtDateTime, fmtSigned } from "@/components/fw/format"
import { listModelVersions, promoteModelVersion, vetoModelVersion, type RegisteredModel } from "@/lib/platform-api"

const TONE = { promoted: "ok", candidate: "info", retired: "off", rejected: "danger" } as const

function skill(m: RegisteredModel): number | null {
  const real = (m.metrics as { real?: { skill_vs_persistence?: number } } | null)?.real
  return typeof real?.skill_vs_persistence === "number" ? real.skill_vs_persistence : null
}

export default function ModelsPage() {
  const [versions, setVersions] = useState<RegisteredModel[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [vetoing, setVetoing] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    try {
      setVersions(await listModelVersions())
      setError(null)
      setNow(Date.now())
    } catch (e) {
      setError(e)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  const act = async (id: number, fn: () => Promise<RegisteredModel>, done: (m: RegisteredModel) => string) => {
    setBusy(id)
    try {
      toast.success(done(await fn()))
      setVetoing(null)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  if (error) return <ApiError error={error} onRetry={load} />
  if (!versions) return <SkeletonRows />
  if (!versions.length) {
    return (
      <Card>
        <EmptyState title="No model versions yet">
          A finished training run becomes a version within a few minutes; promote one from its run page or here.
        </EmptyState>
      </Card>
    )
  }

  const groups = new Map<string, RegisteredModel[]>()
  for (const v of versions) {
    const key = `${v.energy_type}-${v.horizon}`
    groups.set(key, [...(groups.get(key) ?? []), v])
  }

  return (
    <div className="space-y-6">
      {[...groups.entries()].map(([key, list]) => (
        <Card
          key={key}
          title={
            <span className="flex items-center gap-2">
              <EnergyIcon type={list[0].energy_type} />
              <span className="capitalize">{list[0].energy_type}</span>, {list[0].horizon} h ahead
            </span>
          }
          bodyClassName="pt-2"
        >
          <Table>
            <thead>
              <tr>
                <Th>Version</Th>
                <Th>Status</Th>
                <Th>Training run</Th>
                <Th right>Skill</Th>
                <Th>Gates</Th>
                <Th>Promoted</Th>
                <Th right> </Th>
              </tr>
            </thead>
            <tbody>
              {list.map((v) => {
                const id = v.id as number
                const vetoOpen = v.status === "promoted" && v.veto_until && Date.parse(v.veto_until) > now
                return (
                  <Tr key={id}>
                    <Td mono>v{v.version}</Td>
                    <Td>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <StatusPill tone={TONE[v.status ?? "candidate"]}>{v.status}</StatusPill>
                        {v.origin === "schedule" && <StatusPill tone="none">scheduled</StatusPill>}
                      </div>
                      {v.note && <div className="mt-1 max-w-[260px] text-xs text-fw-muted">{v.note}</div>}
                    </Td>
                    <Td>
                      <Link href={`/training/${v.run_id}`} className="fw-num block max-w-[220px] truncate text-sm underline-offset-2 hover:underline" title={v.run_id}>
                        {v.run_id}
                      </Link>
                      {v.data_percent != null && v.data_percent < 100 && (
                        <div className="text-xs text-fw-muted">{v.data_percent}% of the data</div>
                      )}
                    </Td>
                    <Td right mono>{fmtSigned(skill(v), 3)}</Td>
                    <Td>
                      {v.gates ? (
                        <ul className="space-y-0.5 text-xs">
                          {v.gates.gates.map((g) => (
                            <li key={g.name} className="flex items-start gap-1" title={g.detail}>
                              {g.passed ? <Check className="mt-0.5 h-3 w-3 text-ok" /> : <X className="mt-0.5 h-3 w-3 text-fw-accent-dark" />}
                              <span>{g.name}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="text-xs text-fw-muted">—</span>
                      )}
                    </Td>
                    <Td className="text-sm">
                      {v.promoted_at ? (
                        <>
                          <div className="fw-num">{fmtDateTime(v.promoted_at)}</div>
                          <div className="text-xs text-fw-muted">{v.promoted_by}</div>
                          {vetoOpen && (
                            <div className="text-xs text-fw-accent-dark">
                              can be vetoed for {Math.max(1, Math.ceil((Date.parse(v.veto_until as string) - now) / 3_600_000))} h more
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="text-fw-muted">—</span>
                      )}
                    </Td>
                    <Td right>
                      {vetoing === id ? (
                        <ConfirmWithReason
                          action="Veto"
                          placeholder="Why (kept in the audit log)"
                          busy={busy === id}
                          onCancel={() => setVetoing(null)}
                          onConfirm={(note) => act(id, () => vetoModelVersion(id, note), (m) => `Vetoed; v${m.version} serves forecasts again`)}
                        />
                      ) : vetoOpen ? (
                        <Pill size="s" variant="outline" onClick={() => setVetoing(id)}>
                          Veto
                        </Pill>
                      ) : v.status === "candidate" || v.status === "retired" ? (
                        <Pill
                          size="s"
                          variant={v.status === "candidate" ? "primary" : "outline"}
                          loading={busy === id}
                          onClick={() => act(id, () => promoteModelVersion(id), (m) => `v${m.version} now serves ${m.energy_type} forecasts ${m.horizon} h ahead`)}
                        >
                          {v.status === "retired" ? "Roll back to this" : "Promote"}
                        </Pill>
                      ) : null}
                    </Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
        </Card>
      ))}
      <p className="text-sm text-fw-muted">
        Scheduled runs are promoted automatically when every gate passes: trained on all data, beats persistence, beats the
        current model, and no site more than 10 % worse. You can veto that for 24 hours. Gates are shown for manual promotions but not enforced.
      </p>
    </div>
  )
}
