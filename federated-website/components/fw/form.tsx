"use client"

// Form pieces (APP_PAGES_SPEC.md §1.7): fields, inputs, segmented control, toggle cards, sticky bar.

import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react"
import { ChevronDown, Lock } from "lucide-react"
import { cn } from "@/lib/utils"

const CONTROL =
  "w-full rounded-[12px] border border-line-strong bg-white px-3.5 text-base text-ink placeholder:text-[#a3a3a3] " +
  "transition-[border-color,box-shadow] outline-none focus:border-ink focus:shadow-[0_0_0_3px_rgba(255,63,16,0.2)] " +
  "disabled:bg-paper-warm disabled:text-fw-muted aria-[invalid=true]:border-fw-accent-dark"

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { mono?: boolean }>(function Input(
  { className, mono, ...rest },
  ref,
) {
  return <input ref={ref} className={cn(CONTROL, "h-11", mono && "fw-num", className)} {...rest} />
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cn(CONTROL, "min-h-24 py-2.5", className)} {...rest} />
})

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select className={cn(CONTROL, "h-11 appearance-none pr-9", className)} {...rest}>
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fw-muted" aria-hidden />
    </div>
  )
}

/** Label above, help below; an error replaces the help. Children get the id. */
export function Field({
  label,
  help,
  error,
  children,
  className,
  htmlFor,
  aside,
}: {
  label: ReactNode
  help?: ReactNode
  error?: ReactNode
  children: ReactNode
  className?: string
  htmlFor?: string
  aside?: ReactNode
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <label htmlFor={htmlFor} className="text-sm font-medium leading-5 text-ink">
          {label}
        </label>
        {aside}
      </div>
      {children}
      {error ? (
        <p className="mt-1.5 text-[13px] leading-[18px] text-fw-accent-dark">{error}</p>
      ) : help ? (
        <p className="mt-1.5 text-[13px] leading-[18px] text-fw-muted">{help}</p>
      ) : null}
    </div>
  )
}

/** Two columns on desktop: title + one line of help at the left third, fields at the right. */
export function FormSection({ title, help, children }: { title: ReactNode; help?: ReactNode; children: ReactNode }) {
  return (
    <section className="grid gap-6 border-t border-line py-8 first:border-t-0 first:pt-0 md:grid-cols-3 md:gap-10">
      <div>
        <h2 className="text-xl font-medium leading-7 text-ink">{title}</h2>
        {help && <p className="mt-1 text-sm leading-5 text-fw-muted">{help}</p>}
      </div>
      <div className="space-y-5 md:col-span-2">{children}</div>
    </section>
  )
}

export function Segmented<T extends string | number>({
  value,
  onChange,
  options,
  ariaLabel,
  size = "m",
  className,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[]
  ariaLabel: string
  size?: "s" | "m"
  className?: string
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={cn("inline-flex rounded-full bg-surface p-1", className)}>
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={o.disabled}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full font-medium transition-[background-color,box-shadow,color] disabled:cursor-not-allowed disabled:opacity-40",
              size === "s" ? "h-7 px-3 text-sm" : "h-9 px-4 text-[15px]",
              on ? "bg-white text-ink shadow-[0_0_0_1px_var(--fw-line),0_1px_2px_rgba(0,0,0,0.04)]" : "text-fw-muted hover:text-ink",
            )}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

export function Switch({ checked, onChange, disabled, label }: { checked: boolean; onChange?: (v: boolean) => void; disabled?: boolean; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange?.(!checked)}
      className={cn(
        "relative inline-flex h-6 w-10 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed",
        checked ? "bg-ink" : "bg-[#d4d4d2]",
        disabled && checked && "bg-[#5a5a5a]",
      )}
    >
      <span className={cn("inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
    </button>
  )
}

/** Consent card: title, one sentence, switch at the right; locked when required. */
export function ToggleCard({
  title,
  description,
  checked,
  onChange,
  locked,
  lockedNote = "Required to join",
}: {
  title: ReactNode
  description: ReactNode
  checked: boolean
  onChange?: (v: boolean) => void
  locked?: boolean
  lockedNote?: string
}) {
  const id = useId()
  return (
    <div className={cn("flex items-start gap-4 rounded-[16px] border border-line p-4 transition-colors", checked && "bg-paper-warm/60")}>
      <div className="min-w-0 flex-1">
        <div id={id} className="flex items-center gap-2 text-[15px] font-medium text-ink">
          {title}
          {locked && (
            <span className="inline-flex items-center gap-1 text-xs font-normal text-fw-muted">
              <Lock className="h-3 w-3" aria-hidden />
              {lockedNote}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm leading-5 text-fw-muted">{description}</p>
      </div>
      <Switch checked={checked} onChange={locked ? undefined : onChange} disabled={locked} label={typeof title === "string" ? title : "Toggle"} />
    </div>
  )
}

/** White bar stuck to the bottom of long forms: Cancel + the primary action. */
export function StickyBar({ children, note }: { children: ReactNode; note?: ReactNode }) {
  return (
    <div className="sticky bottom-0 z-20 -mx-5 mt-8 border-t border-line bg-white/95 px-5 py-4 backdrop-blur sm:-mx-10 sm:px-10">
      <div className="flex flex-wrap items-center justify-end gap-3">
        {note && <div className="mr-auto min-w-0 text-sm">{note}</div>}
        {children}
      </div>
    </div>
  )
}
