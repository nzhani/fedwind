import { redirect } from "next/navigation"

// The legacy upload-and-train dashboard became /experiments (plan T4.3).
export default function DashboardPage() {
  redirect("/experiments")
}
