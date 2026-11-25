"use client"

// Floating white nav pill (DESIGN_SPEC.md §4.1) with the account area at its right end.

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { BellRing, ChevronDown, LogOut, Menu, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth"
import { Wordmark } from "@/components/fw/mark"
import { PillLink, Roll } from "@/components/fw/button"
import { TelegramSheet } from "@/components/telegram-sheet"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

const MORE = [
  { href: "/about", label: "About" },
  { href: "/architecture", label: "Architecture" },
  { href: "/solar", label: "Solar forecasting" },
  { href: "/data-source", label: "Data source" },
  { href: "/instructions", label: "Instructions" },
]

const isActive = (pathname: string, href: string) =>
  href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`)

function useLinks() {
  const { user, isAdmin } = useAuth()
  const links = [{ href: "/forecast", label: "Forecast" }]
  if (user && (isAdmin || user.role === "operator")) links.push({ href: "/sites", label: isAdmin ? "Plants" : "Your plants" })
  links.push({ href: "/training", label: "Training" }, { href: "/experiments", label: "Experiments" })
  if (isAdmin) links.push({ href: "/admin", label: "Admin" })
  return links
}

function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname()
  const active = isActive(pathname, href)
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative rounded-full px-3 py-1.5 text-base font-medium tracking-[-0.01em] transition-colors",
        active ? "bg-surface text-ink" : "text-ink/80 hover:text-ink",
      )}
    >
      <Roll>{label}</Roll>
    </Link>
  )
}

function Account() {
  const { user, loading, logout, isAdmin } = useAuth()
  const pathname = usePathname()
  const router = useRouter()
  const [alertsOpen, setAlertsOpen] = useState(false)
  if (loading) return <div className="h-9 w-24" aria-hidden />
  if (!user) {
    return (
      <div className="flex items-center gap-1">
        <Link
          href={`/login?next=${encodeURIComponent(pathname === "/login" ? "/" : pathname)}`}
          className="group hidden rounded-full px-3 py-1.5 text-base font-medium text-fw-accent-dark sm:inline-flex"
        >
          <Roll>Log in</Roll>
        </Link>
        <PillLink href="/register" size="s" arrow>
          Register plant
        </PillLink>
      </div>
    )
  }
  const initials = user.name
    .split(/\s+/)
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()
  return (
    <>
    <TelegramSheet open={alertsOpen} onOpenChange={setAlertsOpen} role={user.role} />
    <DropdownMenu>
      <DropdownMenuTrigger className="group flex items-center gap-2 rounded-full py-1 pl-1 pr-2.5 text-left outline-none transition-colors hover:bg-paper-warm data-[state=open]:bg-paper-warm">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-ink text-xs font-medium text-white">{initials}</span>
        <span className="hidden max-w-[150px] flex-col leading-tight sm:flex">
          <span className="truncate text-sm font-medium text-ink">{user.name}</span>
          <span className="truncate text-xs capitalize text-fw-muted">{user.role}</span>
        </span>
        <ChevronDown className="h-4 w-4 text-fw-muted" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={10} className="w-60 rounded-[14px] border-line p-1.5 shadow-[0_12px_32px_rgba(34,34,34,0.12)]">
        <DropdownMenuLabel className="px-2.5 py-2">
          <div className="truncate text-sm font-medium">{user.name}</div>
          <div className="truncate text-xs font-normal text-fw-muted">{user.email}</div>
          {user.organization && <div className="mt-0.5 truncate text-xs font-normal text-fw-muted">{user.organization.name}</div>}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(isAdmin || user.role === "operator") && (
          <DropdownMenuItem className="rounded-[10px] px-2.5 py-2" onSelect={() => router.push("/sites")}>
            {isAdmin ? "Plants" : "Your plants"}
          </DropdownMenuItem>
        )}
        {user.role === "operator" && (
          <DropdownMenuItem className="rounded-[10px] px-2.5 py-2" onSelect={() => router.push("/sites/new")}>
            Register a plant
          </DropdownMenuItem>
        )}
        {isAdmin && (
          <DropdownMenuItem className="rounded-[10px] px-2.5 py-2" onSelect={() => router.push("/admin")}>
            Admin overview
          </DropdownMenuItem>
        )}
        <DropdownMenuItem className="rounded-[10px] px-2.5 py-2" onSelect={() => setAlertsOpen(true)}>
          <BellRing className="h-4 w-4" aria-hidden />
          Telegram alerts
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="rounded-[10px] px-2.5 py-2"
          onSelect={async () => {
            await logout()
            router.push("/")
          }}
        >
          <LogOut className="h-4 w-4" aria-hidden />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    </>
  )
}

export function Navbar() {
  const pathname = usePathname()
  const links = useLinks()
  const [open, setOpen] = useState(false)
  useEffect(() => setOpen(false), [pathname])

  return (
    <header className="pointer-events-none fixed inset-x-0 top-0 z-50 px-3 pt-2 sm:px-6 sm:pt-3">
      <nav
        aria-label="Main"
        className="pointer-events-auto mx-auto flex h-14 max-w-[1100px] items-center justify-between gap-6 rounded-[38px] bg-white py-2 pl-5 pr-2.5 shadow-[0_3px_6px_rgba(0,0,0,0.05),0_0_0_1px_rgba(34,34,34,0.04)] sm:pl-7"
      >
        <Link href="/" className="rounded-full" aria-label="ArqauQuat home">
          <Wordmark />
        </Link>

        <div className="hidden items-center gap-1 lg:flex">
          {links.map((l) => (
            <NavLink key={l.href} {...l} />
          ))}
          <DropdownMenu>
            <DropdownMenuTrigger
              className={cn(
                "flex items-center gap-1 rounded-full px-3 py-1.5 text-base font-medium outline-none transition-colors data-[state=open]:bg-surface",
                MORE.some((m) => isActive(pathname, m.href)) ? "bg-surface text-ink" : "text-ink/80 hover:text-ink",
              )}
            >
              More
              <ChevronDown className="h-4 w-4" aria-hidden />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="center" sideOffset={14} className="w-52 rounded-[14px] border-line p-1.5 shadow-[0_12px_32px_rgba(34,34,34,0.12)]">
              {MORE.map((m) => (
                <DropdownMenuItem key={m.href} asChild className="rounded-[10px] px-2.5 py-2">
                  <Link href={m.href}>{m.label}</Link>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="flex items-center gap-1">
          <Account />
          <button
            type="button"
            className="ml-1 flex h-10 w-10 items-center justify-center rounded-full text-ink hover:bg-paper-warm lg:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </nav>

      {open && (
        <div className="pointer-events-auto mx-auto mt-2 max-w-[1100px] rounded-[24px] bg-white p-3 shadow-[0_12px_32px_rgba(34,34,34,0.12)] lg:hidden">
          {[{ href: "/", label: "Home" }, ...links, ...MORE].map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={cn(
                "block rounded-[14px] px-4 py-3 text-[22px] font-medium tracking-[-0.01em]",
                isActive(pathname, l.href) ? "bg-surface text-ink" : "text-ink/85",
              )}
            >
              {l.label}
            </Link>
          ))}
          <LoginLinkMobile />
        </div>
      )}
    </header>
  )
}

function LoginLinkMobile() {
  const { user, loading } = useAuth()
  if (loading || user) return null
  return (
    <Link href="/login" className="block rounded-[14px] px-4 py-3 text-[22px] font-medium text-fw-accent-dark">
      Log in
    </Link>
  )
}
