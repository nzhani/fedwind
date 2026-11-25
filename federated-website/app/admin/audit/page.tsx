"use client"

// Audit log (APP_PAGES_SPEC.md §3.6): filter by group and target, cursor paging, CSV export.

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { Card, Table, Td, Th, Tr } from "@/components/fw/surface"
import { Pill, TextAction } from "@/components/fw/button"
import { Input, Segmented } from "@/components/fw/form"
import { ApiError, EmptyState, SkeletonRows } from "@/components/fw/feedback"
import { fmtDateTime } from "@/components/fw/format"
import { SECURITY_ACTIONS, actorLabel, targetHref } from "@/components/audit-line"
import { cn } from "@/lib/utils"
import { getAuditPage, type AuditEntry } from "@/lib/platform-api"

const GROUPS = [
  { value: "", label: "All" },
  { value: "site.", label: "Sites" },
  { value: "login.", label: "Logins" },
  { value: "user.", label: "Users" },
  { value: "run.", label: "Runs" },
  { value: "model.", label: "Models" },
]

function details(d: Record<string, unknown>): string {
  return Object.entries(d ?? {})
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ")
}

export default function AuditPage() {
  const [group, setGroup] = useState("")
  const [target, setTarget] = useState("")
  const [entries, setEntries] = useState<AuditEntry[] | null>(null)
  const [next, setNext] = useState<number | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(
    async (before?: number | null) => {
      setBusy(true)
      try {
        const page = await getAuditPage({ limit: 50, action: group || undefined, target: target.trim() || undefined, before })
        setEntries((cur) => (before ? [...(cur ?? []), ...page.entries] : page.entries))
        setNext(page.next_before)
        setError(null)
      } catch (e) {
        setError(e)
      } finally {
        setBusy(false)
      }
    },
    [group, target],
  )

  useEffect(() => {
    const t = setTimeout(() => load(), target ? 300 : 0)
    return () => clearTimeout(t)
  }, [load, target])

  const exportCsv = () => {
    if (!entries?.length) return
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`
    const lines = [
      ["time_utc", "actor", "action", "target", "details", "ip"].join(","),
      ...entries.map((e) => [e.at, actorLabel(e), e.action, e.target ?? "", details(e.details), e.ip ?? ""].map(esc).join(",")),
    ]
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }))
    const a = document.createElement("a")
    a.href = url
    a.download = `fedwind-audit-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center">
        <Segmented ariaLabel="Action group" value={group} onChange={setGroup} options={GROUPS} />
        <Input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="Target (site id, run id, email)"
          aria-label="Filter by target"
          className="fw-num lg:w-[320px]"
        />
        <div className="lg:ml-auto">
          <TextAction onClick={exportCsv} arrow={false}>
            Export CSV
          </TextAction>
        </div>
      </div>
      {error ? <ApiError error={error} onRetry={() => load()} className="mb-6" /> : null}
      <Card bodyClassName="pt-2">
        {!entries ? (
          <div className="pt-4">
            <SkeletonRows rows={6} />
          </div>
        ) : entries.length === 0 ? (
          <EmptyState title="No entries">Nothing matches these filters.</EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Time</Th>
                <Th>Actor</Th>
                <Th>Action</Th>
                <Th>Target</Th>
                <Th>Details</Th>
                <Th>IP</Th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const href = targetHref(e)
                const d = details(e.details)
                return (
                  <Tr key={e.id}>
                    <Td mono className="whitespace-nowrap text-[13px]">
                      <span title={fmtDateTime(e.at, { utc: true, seconds: true })}>{fmtDateTime(e.at, { seconds: true })}</span>
                    </Td>
                    <Td className="max-w-[160px] truncate">{actorLabel(e)}</Td>
                    <Td mono className={cn("whitespace-nowrap text-[13px]", SECURITY_ACTIONS.has(e.action) && "text-fw-accent-dark")}>
                      {e.action}
                    </Td>
                    <Td mono className="max-w-[220px] truncate text-[13px]">
                      {e.target ? (
                        href ? (
                          <Link href={href} className="underline-offset-4 hover:underline" title={e.target}>
                            {e.target}
                          </Link>
                        ) : (
                          <span title={e.target}>{e.target}</span>
                        )
                      ) : (
                        "—"
                      )}
                    </Td>
                    <Td className="max-w-[280px] truncate text-[13px] text-fw-muted">
                      <span title={d}>{d || "—"}</span>
                    </Td>
                    <Td mono className="whitespace-nowrap text-[13px] text-fw-muted">
                      {e.ip ?? "—"}
                    </Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
        )}
        {next && (
          <div className="mt-6 flex justify-center">
            <Pill variant="outline" size="s" loading={busy} onClick={() => load(next)}>
              Load older
            </Pill>
          </div>
        )}
      </Card>
    </div>
  )
}
