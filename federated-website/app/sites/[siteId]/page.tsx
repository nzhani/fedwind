"use client"

// Plant page (APP_PAGES_SPEC.md §2.3): progress stepper, the site kit while approved, then the live
// connection and the plant's power forecast. Polls every 5 s so "Online" shows up by itself.

import { useCallback, useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { Pencil } from "lucide-react"
import { AppPage, Card, PageHeader } from "@/components/fw/surface"
import { Pill } from "@/components/fw/button"
import { ApiError, Gate, Skeleton, Stepper, toast, type Step } from "@/components/fw/feedback"
import { SitePill } from "@/components/fw/status"
import { fmtDateTime, fmtPower } from "@/components/fw/format"
import {
  ActivityCard,
  ConnectionCard,
  ConsentsCard,
  DetailsCard,
  ForecastPreview,
  KitCard,
  SiteAdminActions,
  StatusNotice,
  adminActionsFor,
} from "@/components/site-panels"
import { SiteForm } from "@/components/site-form"
import { useAuth } from "@/lib/auth"
import { getMySite, PlatformApiError, updateMySite, type SiteDetail } from "@/lib/platform-api"

function progressSteps(site: SiteDetail): Step[] {
  const p = site.progress ?? {}
  const c = site.connection
  const online = c?.state === "online"
  const offline = c?.state === "offline"
  const steps: Step[] = [
    { label: "Registered", at: p.registered_at ?? site.created_at, done: true },
    { label: "Approved", at: p.approved_at, done: Boolean(p.approved_at) },
    { label: "Kit installed", at: p.enrolled_at, done: Boolean(p.enrolled_at) },
    { label: offline ? "Offline" : "Online", at: online ? p.online_at : offline ? c?.last_heartbeat_at : null, done: online },
  ]
  const current = steps.findIndex((s) => !s.done)
  steps[current === -1 ? steps.length - 1 : current].current = true
  return steps
}

export default function PlantPage() {
  const { siteId } = useParams<{ siteId: string }>()
  const { user, loading: authLoading, isAdmin } = useAuth()
  const [site, setSite] = useState<SiteDetail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [editing, setEditing] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    try {
      setSite(await getMySite(siteId))
      setError(null)
      setNow(Date.now())
    } catch (e) {
      setError(e)
    }
  }, [siteId])

  useEffect(() => {
    if (!user) return
    load()
    const t = setInterval(() => {
      if (document.visibilityState === "visible") load()
    }, 5_000)
    return () => clearInterval(t)
  }, [user, load])

  const back = { href: isAdmin ? "/admin/sites" : "/sites", label: isAdmin ? "All sites" : "Your plants" }

  if (authLoading || (user && !site && !error)) {
    return (
      <AppPage>
        <Skeleton className="mb-4 h-5 w-32" />
        <Skeleton className="mb-10 h-12 w-[420px] max-w-full" />
        <Skeleton className="mb-6 h-28 w-full rounded-[16px]" />
        <Skeleton className="h-72 w-full rounded-[16px]" />
      </AppPage>
    )
  }
  if (!user) {
    return (
      <AppPage>
        <PageHeader back={back} title="Plant" />
        <Gate title="Log in to see this plant" login next={`/sites/${siteId}`} />
      </AppPage>
    )
  }
  if (!site) {
    const notFound = error instanceof PlatformApiError && error.status === 404
    return (
      <AppPage>
        <PageHeader back={back} title={notFound ? "Plant not found" : "Plant"} />
        {notFound ? <Gate title="No such plant">It doesn&apos;t exist, or it belongs to another organization.</Gate> : <ApiError error={error} onRetry={load} />}
      </AppPage>
    )
  }

  const plant = site.kind === "plant"
  const canEdit = plant && site.status === "registered" && user.role === "operator"
  const showKit = plant && site.status === "approved" && site.kit?.can_download
  const enrolled = plant && (site.kit?.installed || site.connection?.state === "online" || site.connection?.state === "offline")
  const ended = site.status === "rejected" || site.status === "revoked"

  return (
    <AppPage>
      <PageHeader
        back={back}
        label={plant ? `${site.energy_type === "wind" ? "Wind" : "Solar"} plant` : "Lab site"}
        title={site.name}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <SitePill site={site} />
            <span className="fw-num ml-1 text-sm text-fw-muted">
              {site.id} · {fmtPower(site.capacity_kw)} · {site.timezone}
            </span>
          </div>
        }
        actions={
          canEdit && !editing ? (
            <Pill variant="outline" size="s" icon={<Pencil className="h-4 w-4" />} onClick={() => setEditing(true)}>
              Edit details
            </Pill>
          ) : undefined
        }
      />

      {editing ? (
        <SiteForm
          site={site}
          submitLabel="Save changes"
          cancelHref={`/sites/${site.id}`}
          onSubmit={async (body) => {
            setSite(await updateMySite(site.id, body))
            setEditing(false)
            toast.success("Saved. The admin sees the new details.")
          }}
        />
      ) : (
        <div className="space-y-6">
          {error ? <ApiError error={error} onRetry={load} /> : null}
          <StatusNotice site={site} />

          {plant && !ended && (
            <Card label="Progress">
              <Stepper steps={progressSteps(site)} format={(iso) => fmtDateTime(iso)} />
            </Card>
          )}

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="min-w-0 space-y-6 lg:col-span-2">
              {showKit && <KitCard site={site} onDownloaded={load} />}
              {enrolled && <ConnectionCard site={site} now={now} />}
              <ForecastPreview site={site} />
              <DetailsCard site={site} />
            </div>
            <div className="min-w-0 space-y-6">
              {isAdmin && adminActionsFor(site).length > 0 && (
                <Card label="Admin" title="Decisions">
                  <SiteAdminActions site={site} onChanged={(s) => (setSite(s), load())} />
                </Card>
              )}
              <ActivityCard site={site} now={now} />
              {plant && (
                <ConsentsCard site={site} editable={isAdmin || user.role === "operator"} onChanged={(s) => (setSite(s), load())} />
              )}
            </div>
          </div>
        </div>
      )}
    </AppPage>
  )
}
