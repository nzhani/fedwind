// Formatting shared by the app pages (APP_PAGES_SPEC.md §6: relative in lists, exact in details).

export function relTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—"
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const s = Math.round((now - t) / 1000)
  const future = s < 0
  const a = Math.abs(s)
  let out: string
  if (a < 45) out = `${a} s`
  else if (a < 3600) out = `${Math.round(a / 60)} min`
  else if (a < 86400) out = `${Math.round(a / 3600)} h`
  else out = `${Math.round(a / 86400)} d`
  return future ? `in ${out}` : `${out} ago`
}

export function fmtDateTime(iso: string | null | undefined, opts: { utc?: boolean; seconds?: boolean } = {}): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    // Lab data is historical (2024): show the year whenever it isn't this year
    ...(d.getFullYear() !== new Date().getFullYear() ? { year: "numeric" } : {}),
    hour: "2-digit",
    minute: "2-digit",
    ...(opts.seconds ? { second: "2-digit" } : {}),
    ...(opts.utc ? { timeZone: "UTC" } : {}),
  }) + (opts.utc ? " UTC" : "")
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
}

/** kW -> "100 MW", "2.5 MW", "850 kW" */
export function fmtPower(kw: number | null | undefined, digits?: number): string {
  if (kw == null || Number.isNaN(kw)) return "—"
  if (Math.abs(kw) >= 1000) {
    const mw = kw / 1000
    const d = digits ?? (Math.abs(mw) >= 100 ? 0 : 1)
    return `${mw.toFixed(d).replace(/\.0$/, "")} MW`
  }
  return `${kw.toFixed(digits ?? 0)} kW`
}

export function fmtPct(x: number | null | undefined, digits = 0): string {
  if (x == null || Number.isNaN(x)) return "—"
  return `${(x * 100).toFixed(digits)} %`
}

export function fmtSigned(x: number | null | undefined, digits = 2): string {
  if (x == null || Number.isNaN(x)) return "—"
  return `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(digits)}`
}

export function humanize(code: string): string {
  return code.replace(/[._-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase())
}
