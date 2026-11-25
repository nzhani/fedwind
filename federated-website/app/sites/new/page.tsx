"use client"

// Register a plant (APP_PAGES_SPEC.md §2.2).

import { useRouter } from "next/navigation"
import { AppPage, PageHeader } from "@/components/fw/surface"
import { Gate, SkeletonRows, toast } from "@/components/fw/feedback"
import { SiteForm } from "@/components/site-form"
import { useAuth } from "@/lib/auth"
import { registerSite } from "@/lib/platform-api"

export default function NewSitePage() {
  const { user, loading } = useAuth()
  const router = useRouter()

  const header = (
    <PageHeader
      back={{ href: "/sites", label: "Your plants" }}
      label="Sites"
      title="Register a plant"
      description="An ArqauQuat admin reviews the details. Once approved, you download the site kit and the plant joins the federation."
    />
  )

  if (loading) return <AppPage><SkeletonRows /></AppPage>
  if (!user) {
    return (
      <AppPage>
        {header}
        <Gate title="Log in to register a plant" login next="/sites/new">
          New here? Register your organization first; it takes a minute.
        </Gate>
      </AppPage>
    )
  }
  if (user.role !== "operator") {
    return (
      <AppPage>
        {header}
        <Gate title="Plants are registered by their operators">
          {user.role === "admin" ? "As an admin you review registrations in Admin → Approvals." : "Ask an ArqauQuat admin for operator access."}
        </Gate>
      </AppPage>
    )
  }

  return (
    <AppPage>
      {header}
      <SiteForm
        submitLabel="Register plant"
        onSubmit={async (body) => {
          const site = await registerSite(body)
          toast.success("Plant registered. An admin will review it.")
          router.push(`/sites/${site.id}`)
        }}
      />
    </AppPage>
  )
}
