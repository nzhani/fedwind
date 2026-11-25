"use client"

// Users (APP_PAGES_SPEC.md §3.5): roles inline, enable/disable, add a user in a side sheet.

import { useCallback, useEffect, useState, type FormEvent } from "react"
import { Check, Copy, UserPlus } from "lucide-react"
import { Card, Table, Td, Th, Tr } from "@/components/fw/surface"
import { Pill } from "@/components/fw/button"
import { Field, Input, Select } from "@/components/fw/form"
import { ApiError, Notice, SkeletonRows, toast } from "@/components/fw/feedback"
import { StatusPill } from "@/components/fw/status"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { useAuth } from "@/lib/auth"
import { createUser, listUsers, updateUser, type AccountUser, type Role } from "@/lib/platform-api"

const ROLES: { value: Role; label: string }[] = [
  { value: "admin", label: "Admin" },
  { value: "operator", label: "Operator" },
  { value: "viewer", label: "Viewer" },
]

/** A random first password the admin passes on once; the user should change it. */
function randomPassword(): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("")
}

export default function UsersPage() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState<AccountUser[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [open, setOpen] = useState(false)

  const load = useCallback(async () => {
    try {
      setUsers(await listUsers())
      setError(null)
    } catch (e) {
      setError(e)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const patch = async (u: AccountUser, change: { role?: Role; active?: boolean }) => {
    setBusyId(u.id)
    try {
      await updateUser(u.id, change)
      toast.success(change.role ? `${u.name} is now ${change.role}` : change.active ? `${u.name} can log in again` : `${u.name} is disabled`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <div className="mb-6 flex justify-end">
        <Pill icon={<UserPlus className="h-4 w-4" />} onClick={() => setOpen(true)}>
          Add user
        </Pill>
      </div>
      {error ? <ApiError error={error} onRetry={load} className="mb-6" /> : null}
      <Card bodyClassName="pt-2">
        {!users ? (
          <div className="pt-4">
            <SkeletonRows />
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>User</Th>
                <Th>Organization</Th>
                <Th>Role</Th>
                <Th>Status</Th>
                <Th className="w-32">
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const self = u.id === me?.id
                return (
                  <Tr key={u.id}>
                    <Td>
                      <div className="font-medium">
                        {u.name} {self && <span className="text-sm font-normal text-fw-muted">(you)</span>}
                      </div>
                      <div className="text-sm text-fw-muted">{u.email}</div>
                    </Td>
                    <Td className="text-fw-muted">{u.organization?.name ?? "—"}</Td>
                    <Td>
                      <div className="w-[150px]" title={self ? "You can't change your own access" : undefined}>
                        <Select
                          aria-label={`Role of ${u.name}`}
                          value={u.role}
                          disabled={self || busyId === u.id}
                          onChange={(e) => patch(u, { role: e.target.value as Role })}
                          className="h-9 text-sm"
                        >
                          {ROLES.map((r) => (
                            <option key={r.value} value={r.value}>
                              {r.label}
                            </option>
                          ))}
                        </Select>
                      </div>
                    </Td>
                    <Td>
                      <StatusPill tone={u.active ? "ok" : "off"}>{u.active ? "Active" : "Disabled"}</StatusPill>
                    </Td>
                    <Td className="text-right">
                      {!self && (
                        <Pill size="s" variant={u.active ? "ghost" : "outline"} disabled={busyId === u.id} onClick={() => patch(u, { active: !u.active })}>
                          {u.active ? "Disable" : "Enable"}
                        </Pill>
                      )}
                    </Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
        )}
      </Card>
      <AddUserSheet open={open} onOpenChange={setOpen} onCreated={load} />
    </div>
  )
}

function AddUserSheet({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (v: boolean) => void; onCreated: () => void }) {
  const [form, setForm] = useState({ name: "", email: "", role: "operator" as Role, organization: "" })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null)
  const [copied, setCopied] = useState(false)

  const reset = () => {
    setForm({ name: "", email: "", role: "operator", organization: "" })
    setCreated(null)
    setError(null)
    setCopied(false)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const password = randomPassword()
    try {
      await createUser({ ...form, password, organization: form.role === "operator" ? form.organization || undefined : undefined })
      setCreated({ email: form.email, password })
      onCreated()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v)
        if (!v) reset()
      }}
    >
      <SheetContent side="right" className="w-full border-line p-0 sm:max-w-[480px]">
        <SheetHeader className="px-8 pb-0 pt-8">
          <SheetTitle className="text-2xl font-medium tracking-[-0.01em]">Add user</SheetTitle>
          <SheetDescription>They log in with the first password below and should change it.</SheetDescription>
        </SheetHeader>
        {created ? (
          <div className="space-y-5 px-8 py-6">
            <Notice title={`Created ${created.email}`}>Copy the first password now; it isn&apos;t shown again.</Notice>
            <div className="flex items-center gap-2 rounded-[12px] bg-surface py-2 pl-4 pr-2">
              <code className="fw-num flex-1 text-[15px]">{created.password}</code>
              <button
                type="button"
                className="flex h-8 w-8 items-center justify-center rounded-full hover:bg-white"
                aria-label="Copy password"
                onClick={async () => {
                  await navigator.clipboard.writeText(created.password)
                  setCopied(true)
                }}
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
            <div className="flex gap-2">
              <Pill onClick={reset}>Add another</Pill>
              <Pill variant="ghost" onClick={() => onOpenChange(false)}>
                Done
              </Pill>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-5 px-8 py-6">
            <Field label="Name" htmlFor="u-name">
              <Input id="u-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Email" htmlFor="u-email">
              <Input id="u-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </Field>
            <Field label="Role" htmlFor="u-role">
              <Select id="u-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </Select>
            </Field>
            {form.role === "operator" && (
              <Field label="Organization" htmlFor="u-org" help="Operators manage the plants of their organization">
                <Input id="u-org" required value={form.organization} onChange={(e) => setForm({ ...form, organization: e.target.value })} />
              </Field>
            )}
            {error ? <ApiError error={error} /> : null}
            <Pill type="submit" loading={busy} className="w-full">
              Create user
            </Pill>
          </form>
        )}
      </SheetContent>
    </Sheet>
  )
}
