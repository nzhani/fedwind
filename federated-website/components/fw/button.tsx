"use client"

// Pill buttons (DESIGN_SPEC.md §4.2): S / M / L, the text-roll hover, an optional arrow.

import Link from "next/link"
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react"
import { ArrowRight, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

export type PillVariant = "primary" | "onfill" | "outline" | "ghost" | "danger" | "ink"
export type PillSize = "s" | "m" | "l"

const BASE =
  "group relative inline-flex items-center justify-center rounded-full font-medium whitespace-nowrap select-none " +
  "transition-[background-color,box-shadow,color] duration-150 disabled:pointer-events-none disabled:opacity-45 " +
  "aria-disabled:pointer-events-none aria-disabled:opacity-45"

const SIZES: Record<PillSize, string> = {
  s: "h-9 px-3.5 text-[15px] leading-5 gap-1",
  m: "h-11 px-4 text-base leading-6 gap-1.5",
  l: "h-[52px] px-5 text-lg leading-6 gap-1.5",
}

const VARIANTS: Record<PillVariant, string> = {
  primary: "bg-fw-accent-dark text-white hover:bg-[#bd310a]",
  onfill: "bg-white text-fw-accent-dark hover:bg-paper-warm",
  outline: "bg-white text-ink shadow-[inset_0_0_0_1px_var(--fw-line-strong)] hover:shadow-[inset_0_0_0_1px_var(--fw-ink)]",
  ghost: "text-ink hover:bg-paper-warm",
  danger: "bg-white text-fw-accent-dark shadow-[inset_0_0_0_1px_rgba(210,55,12,0.4)] hover:bg-fw-accent-soft",
  ink: "bg-ink text-white hover:bg-black",
}

export function pillClass(variant: PillVariant = "primary", size: PillSize = "m", className?: string) {
  return cn(BASE, SIZES[size], VARIANTS[variant], className)
}

/** The label twice: the second copy rolls in on hover (CSS in globals.css, off for reduced motion). */
export function Roll({ children }: { children: ReactNode }) {
  return (
    <span className="fw-roll">
      <span>{children}</span>
      <span aria-hidden>{children}</span>
    </span>
  )
}

interface PillContentProps {
  children: ReactNode
  arrow?: boolean
  icon?: ReactNode
  loading?: boolean
  size?: PillSize
}

function PillContent({ children, arrow, icon, loading, size = "m" }: PillContentProps) {
  const iconSize = size === "l" ? "h-[18px] w-[18px]" : "h-4 w-4"
  return (
    <>
      {loading ? <Loader2 className={cn(iconSize, "animate-spin")} aria-hidden /> : icon}
      <Roll>
        {children}
        {arrow && <ArrowRight className={iconSize} aria-hidden strokeWidth={1.75} />}
      </Roll>
    </>
  )
}

type PillProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: PillVariant
  size?: PillSize
  arrow?: boolean
  icon?: ReactNode
  loading?: boolean
}

export const Pill = forwardRef<HTMLButtonElement, PillProps>(function Pill(
  { variant = "primary", size = "m", arrow, icon, loading, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button ref={ref} type={type} disabled={disabled || loading} className={pillClass(variant, size, className)} {...rest}>
      <PillContent arrow={arrow} icon={icon} loading={loading} size={size}>
        {children}
      </PillContent>
    </button>
  )
})

export function PillLink({
  href,
  variant = "primary",
  size = "m",
  arrow,
  icon,
  className,
  children,
  external,
  ...rest
}: {
  href: string
  variant?: PillVariant
  size?: PillSize
  arrow?: boolean
  icon?: ReactNode
  className?: string
  children: ReactNode
  external?: boolean
  onClick?: () => void
}) {
  const content = (
    <PillContent arrow={arrow} icon={icon} size={size}>
      {children}
    </PillContent>
  )
  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={pillClass(variant, size, className)} {...rest}>
        {content}
      </a>
    )
  }
  return (
    <Link href={href} className={pillClass(variant, size, className)} {...rest}>
      {content}
    </Link>
  )
}

/** Quiet text action ("View all →", "Open →"): ink, text roll, optional arrow. */
export function TextAction({
  href,
  onClick,
  children,
  arrow = true,
  tone = "ink",
  className,
}: {
  href?: string
  onClick?: () => void
  children: ReactNode
  arrow?: boolean
  tone?: "ink" | "accent" | "muted"
  className?: string
}) {
  const cls = cn(
    "group inline-flex items-center gap-1 text-sm font-medium rounded-sm",
    tone === "accent" ? "text-fw-accent-dark" : tone === "muted" ? "text-fw-muted hover:text-ink" : "text-ink",
    className,
  )
  const content = (
    <Roll>
      {children}
      {arrow && <ArrowRight className="h-3.5 w-3.5" aria-hidden strokeWidth={1.75} />}
    </Roll>
  )
  if (href) {
    return (
      <Link href={href} className={cls}>
        {content}
      </Link>
    )
  }
  return (
    <button type="button" onClick={onClick} className={cls}>
      {content}
    </button>
  )
}
