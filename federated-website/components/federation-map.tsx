"use client"

// Map of the federation: Kazakhstan (Natural Earth outline, no tiles) with every site as a dot.
// Wind ink, solar orange; lab sites hollow, plants filled; with `live`, online plants pulse green,
// offline ones turn grey, plants not active yet are dashed.

import Link from "next/link"
import { useState } from "react"
import { cn } from "@/lib/utils"
import { KZ_FRAME, KZ_LAKES, KZ_OUTLINE, kzProject } from "@/components/fw/kz-map-data"
import { fmtPower } from "@/components/fw/format"
import type { EnergyType, SiteConnection, SiteStatus } from "@/lib/platform-api"

export interface MapSite {
  id: string
  name: string
  energy_type: EnergyType
  kind: "builtin" | "plant"
  lat: number
  lon: number
  capacity_kw: number | null
  status: SiteStatus
  connection?: SiteConnection | null
}

const CITIES: [string, number, number][] = [
  ["Astana", 51.17, 71.43],
  ["Almaty", 43.24, 76.95],
]

const COLOR: Record<EnergyType, string> = { wind: "#222222", solar: "#ff3f10" }

type Look = "online" | "offline" | "pending" | "plain"

function look(s: MapSite, live: boolean): Look {
  if (s.kind !== "plant" || !live) return "plain"
  if (s.status !== "active") return "pending"
  return s.connection?.state === "online" ? "online" : "offline"
}

function describe(s: MapSite, l: Look): string {
  const what = `${s.energy_type === "wind" ? "Wind" : "Solar"} ${s.kind === "plant" ? "plant" : "lab site"}`
  const state = { online: "online", offline: "offline", pending: s.status === "registered" ? "waiting for approval" : s.status, plain: "" }[l]
  return [what, s.capacity_kw ? fmtPower(s.capacity_kw) : null, state].filter(Boolean).join(" · ")
}

export function FederationMap({
  sites,
  live = false,
  hrefFor,
  className,
}: {
  sites: MapSite[]
  live?: boolean
  hrefFor?: (s: MapSite) => string | null
  className?: string
}) {
  const [hover, setHover] = useState<string | null>(null)
  const W = KZ_FRAME.width
  const H = KZ_FRAME.height
  const shown = sites.find((s) => s.id === hover)

  return (
    <figure className={cn("relative", className)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`Map of Kazakhstan with ${sites.length} federation sites`}>
        <path d={KZ_OUTLINE} fill="#f7f4f1" stroke="rgba(34,34,34,0.18)" strokeWidth={1.2} strokeLinejoin="round" />
        {KZ_LAKES.map((d, i) => (
          <path key={i} d={d} fill="#ffffff" stroke="rgba(34,34,34,0.12)" strokeWidth={0.8} />
        ))}
        {CITIES.map(([name, lat, lon]) => {
          const [x, y] = kzProject(lat, lon)
          return (
            <g key={name} aria-hidden>
              <rect x={x - 2.5} y={y - 2.5} width={5} height={5} fill="#a3a3a3" />
              <text x={x + 8} y={y + 4} fontSize={14} fill="#8a8a8a" fontFamily="var(--font-geist)">
                {name}
              </text>
            </g>
          )
        })}
        {sites.map((s) => {
          const [x, y] = kzProject(s.lat, s.lon)
          const l = look(s, live)
          const plant = s.kind === "plant"
          const color = l === "offline" ? "#a3a3a3" : COLOR[s.energy_type]
          const r = plant ? 9 : 7
          const href = hrefFor?.(s) ?? null
          const dot = (
            <g
              onMouseEnter={() => setHover(s.id)}
              onMouseLeave={() => setHover((h) => (h === s.id ? null : h))}
              onFocus={() => setHover(s.id)}
              onBlur={() => setHover((h) => (h === s.id ? null : h))}
              className="cursor-pointer"
            >
              <circle cx={x} cy={y} r={18} fill="transparent" />
              {l === "online" && (
                <circle cx={x} cy={y} r={r} fill="none" stroke="#1f9d55" strokeWidth={2} className="motion-safe:animate-[fw-ping_2s_ease-out_infinite]" style={{ transformOrigin: `${x}px ${y}px` }} />
              )}
              <circle
                cx={x}
                cy={y}
                r={r}
                fill={plant && l !== "pending" ? color : "#ffffff"}
                stroke={l === "online" ? "#1f9d55" : color}
                strokeWidth={plant ? 2.5 : 2.5}
                strokeDasharray={l === "pending" ? "3 3" : undefined}
              />
              {hover === s.id && <circle cx={x} cy={y} r={r + 5} fill="none" stroke={color} strokeOpacity={0.35} strokeWidth={2} />}
            </g>
          )
          return href ? (
            <Link key={s.id} href={href} aria-label={`${s.name}: ${describe(s, l)}`}>
              {dot}
            </Link>
          ) : (
            <g key={s.id} tabIndex={0} role="img" aria-label={`${s.name}: ${describe(s, l)}`}>
              {dot}
            </g>
          )
        })}
      </svg>

      {shown && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[calc(100%+14px)] whitespace-nowrap rounded-[10px] border border-line bg-white px-3 py-2 text-sm shadow-[0_12px_32px_rgba(34,34,34,0.12)]"
          style={{
            left: `${(kzProject(shown.lat, shown.lon)[0] / W) * 100}%`,
            top: `${(kzProject(shown.lat, shown.lon)[1] / H) * 100}%`,
          }}
          role="tooltip"
        >
          <div className="font-medium text-ink">{shown.name}</div>
          <div className="text-xs text-fw-muted">{describe(shown, look(shown, live))}</div>
        </div>
      )}

      <figcaption className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-fw-muted">
        <LegendDot fill="#222222" /> Wind
        <LegendDot fill="#ff3f10" /> Solar
        <LegendDot fill="#ffffff" stroke="#222222" /> Lab site
        <LegendDot fill="#222222" /> Plant
        {live && (
          <>
            <LegendDot fill="#222222" stroke="#1f9d55" /> Online
            <LegendDot fill="#a3a3a3" /> Offline
            <LegendDot fill="#ffffff" stroke="#222222" dashed /> Not active yet
          </>
        )}
      </figcaption>
    </figure>
  )
}

function LegendDot({ fill, stroke, dashed }: { fill: string; stroke?: string; dashed?: boolean }) {
  return (
    <svg viewBox="0 0 16 16" className="-mr-3 h-3.5 w-3.5" aria-hidden>
      <circle cx={8} cy={8} r={5.5} fill={fill} stroke={stroke ?? fill} strokeWidth={2} strokeDasharray={dashed ? "2 2" : undefined} />
    </svg>
  )
}
