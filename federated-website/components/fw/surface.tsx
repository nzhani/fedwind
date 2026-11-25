"use client"

// App surfaces (APP_PAGES_SPEC.md §1): page frame, page header, cards, stat tiles, tabs, tables.

import Link from "next/link"
import { usePathname } from "next/navigation"
import type { ReactNode } from "react"
import { ArrowLeft } from "lucide-react"
import { cn } from "@/lib/utils"

/** 1200 px content, 40 px sides (20 on phones), clears the floating nav. */
export function AppPage({ children, className, narrow }: { children: ReactNode; className?: string; narrow?: boolean }) {
  return (
    <div className={cn("mx-auto w-full px-5 pb-24 pt-[104px] sm:px-10", narrow ? "max-w-[880px]" : "max-w-[1280px]", className)}>
      {children}
    </div>
  )
}

export function PageHeader({
  label,
  title,
  description,
  actions,
  back,
  meta,
  className,
}: {
  label?: ReactNode
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  back?: { href: string; label: string }
  meta?: ReactNode
  className?: string
}) {
  return (
    <header className={cn("mb-10 sm:mb-12", className)}>
      {back && (
        <Link
          href={back.href}
          className="mb-5 inline-flex items-center gap-1.5 rounded-sm text-sm font-medium text-fw-muted transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} />
          {back.label}
        </Link>
      )}
      {label && <div className="fw-label mb-3">{label}</div>}
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="fw-page-title text-ink">{title}</h1>
          {meta && <div className="mt-3">{meta}</div>}
          {description && <p className="mt-3 max-w-[640px] text-base leading-6 text-fw-muted">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  )
}

export function Card({
  title,
  label,
  action,
  children,
  className,
  bodyClassName,
  id,
}: {
  title?: ReactNode
  label?: ReactNode
  action?: ReactNode
  children?: ReactNode
  className?: string
  bodyClassName?: string
  id?: string
}) {
  return (
    <section id={id} className={cn("rounded-[16px] border border-line bg-white", className)}>
      {(title || label || action) && (
        <div className="flex items-start justify-between gap-4 px-6 pt-5">
          <div className="min-w-0">
            {label && <div className="fw-label mb-1">{label}</div>}
            {title && <h2 className="text-base font-medium leading-6 text-ink">{title}</h2>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      <div className={cn("px-6 pb-6", title || label || action ? "pt-4" : "pt-6", bodyClassName)}>{children}</div>
    </section>
  )
}

export function StatTile({ label, value, hint, className }: { label: ReactNode; value: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="fw-label">{label}</div>
      <div className="fw-num mt-2 truncate text-[32px] leading-[38px] tracking-[-0.01em] text-ink">{value}</div>
      {hint && <div className="mt-1 truncate text-sm text-fw-muted">{hint}</div>}
    </div>
  )
}

export function StatRow({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mb-10 grid grid-cols-2 gap-x-6 gap-y-8 sm:grid-cols-4", className)}>{children}</div>
}

/** Text tabs with a 2 px ink underline (admin sub-navigation, §3.1). */
export function TabNav({ tabs }: { tabs: { href: string; label: string; count?: number | null; exact?: boolean }[] }) {
  const pathname = usePathname()
  return (
    <nav aria-label="Section" className="-mt-4 mb-10 flex gap-6 overflow-x-auto overflow-y-hidden shadow-[inset_0_-1px_0_var(--fw-line)]">
      {tabs.map((t) => {
        const active = t.exact ? pathname === t.href : pathname === t.href || pathname.startsWith(`${t.href}/`)
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "inline-flex shrink-0 items-center gap-2 border-b-2 pb-3 text-[15px] font-medium transition-colors",
              active ? "border-ink text-ink" : "border-transparent text-fw-muted hover:text-ink",
            )}
          >
            {t.label}
            {t.count ? <span className="fw-num rounded-full bg-surface px-1.5 text-xs leading-5 text-ink">{t.count}</span> : null}
          </Link>
        )
      })}
    </nav>
  )
}

/** Definition list: labels muted at the left third, values ink. */
export function DefList({ items }: { items: { label: ReactNode; value: ReactNode; mono?: boolean }[] }) {
  return (
    <dl className="divide-y divide-line">
      {items.map((it, i) => (
        <div key={i} className="grid grid-cols-3 gap-4 py-2.5 text-sm">
          <dt className="text-fw-muted">{it.label}</dt>
          <dd className={cn("col-span-2 min-w-0 break-words text-ink", it.mono && "fw-num")}>{it.value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  )
}

// -- tables (§1.5) ------------------------------------------------------------------------------

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("-mx-6 overflow-x-auto", className)}>
      <table className="w-full min-w-[640px] border-collapse text-sm">{children}</table>
    </div>
  )
}

export function Th({ children, className, right }: { children?: ReactNode; className?: string; right?: boolean }) {
  return (
    <th
      scope="col"
      className={cn("fw-label h-10 border-b border-line px-3 text-left align-middle first:pl-6 last:pr-6", right && "text-right", className)}
    >
      {children}
    </th>
  )
}

export function Tr({ children, onClick, className, selected }: { children: ReactNode; onClick?: () => void; className?: string; selected?: boolean }) {
  return (
    <tr
      onClick={onClick}
      className={cn(
        "border-b border-line last:border-b-0 transition-colors",
        onClick && "cursor-pointer hover:bg-paper-warm",
        selected && "bg-paper-warm",
        className,
      )}
    >
      {children}
    </tr>
  )
}

export function Td({ children, className, right, mono }: { children?: ReactNode; className?: string; right?: boolean; mono?: boolean }) {
  return (
    <td className={cn("h-14 px-3 align-middle text-ink first:pl-6 last:pr-6", right && "text-right", mono && "fw-num", className)}>
      {children}
    </td>
  )
}
