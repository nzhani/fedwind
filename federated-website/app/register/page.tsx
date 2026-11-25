"use client"

// Register an organization (SITE_NETWORK_PLAN.md §3): creates the organization and its first
// operator account; plants are registered next and approved by an admin.

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState, type FormEvent } from "react"
import { AuthSplit } from "@/components/auth-split"
import { Pill } from "@/components/fw/button"
import { Field, Input } from "@/components/fw/form"
import { ApiError, toast } from "@/components/fw/feedback"
import { useAuth } from "@/lib/auth"

const MIN_PASSWORD = 10

export default function RegisterPage() {
  const { register } = useAuth()
  const router = useRouter()
  const [form, setForm] = useState({ name: "", organization: "", email: "", password: "", repeat: "" })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value })

  const mismatch = form.repeat.length > 0 && form.password !== form.repeat
  const tooShort = form.password.length > 0 && form.password.length < MIN_PASSWORD

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (mismatch || tooShort) return
    setBusy(true)
    setError(null)
    try {
      await register({ name: form.name.trim(), organization: form.organization.trim(), email: form.email.trim(), password: form.password })
      toast.success(`Welcome, ${form.organization.trim()}. Register your first plant.`)
      router.push("/sites/new")
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }

  return (
    <AuthSplit>
      <div className="fw-label mb-3">Join the federation</div>
      <h1 className="fw-page-title">Register your organization</h1>
      <form onSubmit={submit} className="mt-10 space-y-5">
        <Field label="Organization" htmlFor="org" help="The company that runs the plant">
          <Input id="org" required autoComplete="organization" value={form.organization} onChange={set("organization")} placeholder="Zhanatas Energy LLP" />
        </Field>
        <Field label="Your name" htmlFor="name">
          <Input id="name" required autoComplete="name" value={form.name} onChange={set("name")} />
        </Field>
        <Field label="Work email" htmlFor="email">
          <Input id="email" type="email" required autoComplete="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Password" htmlFor="password" help={`At least ${MIN_PASSWORD} characters`} error={tooShort ? `At least ${MIN_PASSWORD} characters` : undefined}>
          <Input id="password" type="password" required autoComplete="new-password" value={form.password} onChange={set("password")} aria-invalid={tooShort} />
        </Field>
        <Field label="Repeat password" htmlFor="repeat" error={mismatch ? "The two passwords don't match" : undefined}>
          <Input id="repeat" type="password" required autoComplete="new-password" value={form.repeat} onChange={set("repeat")} aria-invalid={mismatch} />
        </Field>
        {error ? <ApiError error={error} /> : null}
        <Pill type="submit" loading={busy} disabled={mismatch || tooShort} className="w-full" arrow>
          Create account
        </Pill>
      </form>

      <div className="mt-10">
        <div className="fw-label mb-4">What happens next</div>
        <ol className="space-y-3">
          {["Register your plant", "An ArqauQuat admin approves it", "Install the site kit; forecasts start"].map((s, i) => (
            <li key={s} className="flex items-center gap-3 text-[15px]">
              <span className="fw-num flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface text-xs">{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
      </div>
      <p className="mt-8 text-sm text-fw-muted">
        Already registered?{" "}
        <Link href="/login" className="font-medium text-fw-accent-dark underline-offset-4 hover:underline">
          Log in
        </Link>
      </p>
    </AuthSplit>
  )
}
