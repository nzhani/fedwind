"use client"

// Footer with big links (DESIGN_SPEC.md §4.7). Hidden on the split login / register screens.

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Roll } from "@/components/fw/button"
import { Wordmark } from "@/components/fw/mark"

const COLUMNS = [
  {
    label: "Explore",
    links: [
      { href: "/forecast", label: "Forecast" },
      { href: "/training", label: "Training" },
      { href: "/experiments", label: "Experiments" },
      { href: "/register", label: "Register a plant" },
    ],
  },
  {
    label: "Learn",
    links: [
      { href: "/about", label: "About" },
      { href: "/architecture", label: "Architecture" },
      { href: "/solar", label: "Solar" },
      { href: "/data-source", label: "Data source" },
      { href: "/instructions", label: "Instructions" },
    ],
  },
]

export function Footer() {
  const pathname = usePathname()
  if (pathname === "/login" || pathname === "/register") return null
  return (
    <footer className="bg-white px-5 pb-12 pt-12 sm:px-12">
      <div className="border-t border-line pt-12">
        <div className="grid gap-12 md:grid-cols-[1fr_1fr_1fr] md:gap-16">
          {COLUMNS.map((col) => (
            <div key={col.label}>
              <div className="mb-5 text-[10px] font-medium uppercase tracking-[0.1em] text-fw-muted">{col.label}</div>
              <ul className="space-y-1.5">
                {col.links.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href} className="group inline-flex rounded-sm text-[23px] font-medium leading-[1.15] tracking-[-0.01em] text-ink md:text-[32px]">
                      <Roll>{l.label}</Roll>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <div>
            <div className="mb-5 text-[10px] font-medium uppercase tracking-[0.1em] text-fw-muted">Project</div>
            <p className="text-base font-medium leading-6 text-ink">
              Federated learning with a frozen GPT-2 for wind and solar power forecasting.
            </p>
            <p className="mt-4 text-base leading-6 text-fw-muted">
              Nazarbayev University
              <br />
              Astana, Kazakhstan
            </p>
          </div>
        </div>
        <div className="mt-16 flex flex-col gap-3 text-sm text-fw-muted sm:flex-row sm:items-center sm:justify-between">
          <Wordmark className="text-ink" />
          <span>© 2026 ArqauQuat · research prototype · data never leaves the plant</span>
        </div>
      </div>
    </footer>
  )
}
