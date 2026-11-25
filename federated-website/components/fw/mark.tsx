// ArqauQuat's mark: a wind turbine standing in front of the sun. The rotor turns and the sun's
// rays slowly circle; both stop under prefers-reduced-motion (globals.css). Two tones: the sun
// takes --mark-sun (accent on white), everything else currentColor; on orange both are white.

import { cn } from "@/lib/utils"

const RAYS = Array.from({ length: 8 }, (_, i) => i * 45)

export function BrandMark({ className, still = false, sunColor }: { className?: string; still?: boolean; sunColor?: string }) {
  const sun = sunColor ?? "var(--mark-sun, currentColor)"
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden className={cn("shrink-0 overflow-visible", className)}>
      {/* sun, up and to the right of the rotor */}
      <g style={{ transformBox: "view-box", transformOrigin: "24px 8px" }} className={cn(!still && "motion-safe:animate-[spin_24s_linear_infinite]")}>
        {RAYS.map((deg) => (
          <rect key={deg} x="23.3" y="0.5" width="1.4" height="2.3" rx="0.7" fill={sun} transform={`rotate(${deg} 24 8)`} />
        ))}
      </g>
      <circle cx="24" cy="8" r="4" fill={sun} />
      {/* tower */}
      <path d="M11.2 15.5 L10.3 30.5 H13.7 L12.8 15.5 Z" fill="currentColor" />
      {/* rotor: three blades around the hub */}
      <g style={{ transformBox: "view-box", transformOrigin: "12px 14px" }} className={cn(!still && "motion-safe:animate-[spin_5s_linear_infinite]")}>
        {[0, 120, 240].map((deg) => (
          <path key={deg} d="M12 14 C11 11.5 11.2 7.6 12.25 4.9 C12.45 4.4 13.1 4.5 13.2 5 C13.65 7.9 13.3 11.4 12 14 Z" fill="currentColor" transform={`rotate(${deg} 12 14)`} />
        ))}
      </g>
      <circle cx="12" cy="14" r="1.9" fill="currentColor" />
      <circle cx="12" cy="14" r="0.8" fill={sun} />
    </svg>
  )
}

export function Wordmark({ className, markClassName }: { className?: string; markClassName?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-[19px] font-medium tracking-[-0.02em]", className)}>
      <BrandMark className={cn("h-8 w-8 text-ink [--mark-sun:var(--fw-accent)]", markClassName)} />
      ArqauQuat
    </span>
  )
}
