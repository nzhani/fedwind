"use client"

// Admin frame (APP_PAGES_SPEC.md §3.1): one header, text tabs, admins only.

import { useEffect, useState, type ReactNode } from "react"
import { usePathname } from "next/navigation"
import { AppPage, PageHeader, TabNav } from "@/components/fw/surface"
import { Gate, SkeletonRows } from "@/components/fw/feedback"
import { useAuth } from "@/lib/auth"
import { getAdminOverview } from "@/lib/platform-api"

const TITLES: Record<string, { title: string; description: string }> = {
  "/admin": { title: "Overview", description: "What needs you now, and what happened recently." },
  "/admin/approvals": { title: "Approvals", description: "Plants waiting for a decision. Approving lets the operator download the site kit." },
  "/admin/sites": { title: "All sites", description: "Lab sites and registered plants, with their live connection." },
  "/admin/models": { title: "Models", description: "Every trained model version, its promotion gates, and which one serves forecasts." },
  "/admin/users": { title: "Users", description: "Accounts, roles and access." },
  "/admin/health": { title: "Health", description: "Services, models, forecasts, certificates and backups of this server." },
  "/admin/audit": { title: "Audit log", description: "Every decision and security event: who, what, when." },
}

export default function AdminLayout({ children }: { children: ReactNode }) {
  const { user, loading, isAdmin } = useAuth()
  const pathname = usePathname()
  const [waiting, setWaiting] = useState<number | null>(null)

  useEffect(() => {
    if (!isAdmin) return
    const load = () =>
      getAdminOverview()
        .then((o) => setWaiting(o.tiles.waiting))
        .catch(() => undefined)
    load()
    const t = setInterval(load, 15_000)
    return () => clearInterval(t)
  }, [isAdmin, pathname])

  const head = TITLES[pathname] ?? TITLES["/admin"]

  if (loading) return <AppPage><SkeletonRows /></AppPage>
  if (!user || !isAdmin) {
    return (
      <AppPage>
        <PageHeader label="Admin" title="Admin" />
        <Gate title={user ? "This page is for admins" : "Log in as an admin"} login={!user} next={pathname}>
          {user ? "Your account can't open the admin pages." : "The ArqauQuat team approves plants and manages users here."}
        </Gate>
      </AppPage>
    )
  }

  return (
    <AppPage>
      <PageHeader label="Admin" title={head.title} description={head.description} />
      <TabNav
        tabs={[
          { href: "/admin", label: "Overview", exact: true },
          { href: "/admin/approvals", label: "Approvals", count: waiting },
          { href: "/admin/sites", label: "Sites" },
          { href: "/admin/models", label: "Models" },
          { href: "/admin/users", label: "Users" },
          { href: "/admin/audit", label: "Audit log" },
          { href: "/admin/health", label: "Health" },
        ]}
      />
      {children}
    </AppPage>
  )
}
