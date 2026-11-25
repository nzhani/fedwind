"use client"

// Log in (SITE_NETWORK_PLAN.md §3). After login, back to ?next=<path> (same-site paths only).

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState, type FormEvent } from "react"
import { AuthSplit } from "@/components/auth-split"
import { Pill } from "@/components/fw/button"
import { Field, Input } from "@/components/fw/form"
import { ApiError } from "@/components/fw/feedback"
import { useAuth } from "@/lib/auth"

/** Only local paths, so a crafted link can't send people to another site after login. */
function safeNext(role: string): string {
  const next = new URLSearchParams(window.location.search).get("next")
  if (next && next.startsWith("/") && !next.startsWith("//") && next !== "/login") return next
  return role === "admin" ? "/admin" : role === "operator" ? "/sites" : "/forecast"
}

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const user = await login(email.trim(), password)
      router.push(safeNext(user.role))
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }

  return (
    <AuthSplit>
      <div className="fw-label mb-3">Account</div>
      <h1 className="fw-page-title">Log in</h1>
      <p className="mt-3 text-base text-fw-muted">Plant operators and the ArqauQuat team.</p>
      <form onSubmit={submit} className="mt-10 space-y-5">
        <Field label="Email" htmlFor="email">
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password" htmlFor="password">
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {error ? <ApiError error={error} /> : null}
        <Pill type="submit" loading={busy} className="w-full" arrow>
          Log in
        </Pill>
      </form>
      <p className="mt-8 text-sm text-fw-muted">
        New plant?{" "}
        <Link href="/register" className="font-medium text-fw-accent-dark underline-offset-4 hover:underline">
          Register your organization
        </Link>
      </p>
    </AuthSplit>
  )
}
