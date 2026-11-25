"use client"

// Telegram alerts panel (account menu): connect with a one-time t.me link, see the status, disconnect.

import { useCallback, useEffect, useRef, useState } from "react"
import { BellRing, Send } from "lucide-react"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Pill } from "@/components/fw/button"
import { ApiError, Notice, Skeleton, toast } from "@/components/fw/feedback"
import { StatusPill } from "@/components/fw/status"
import { fmtDateTime } from "@/components/fw/format"
import { getTelegram, linkTelegram, unlinkTelegram, type TelegramStatus } from "@/lib/platform-api"

export function TelegramSheet({ open, onOpenChange, role }: { open: boolean; onOpenChange: (v: boolean) => void; role: string }) {
  const [s, setS] = useState<TelegramStatus | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [waiting, setWaiting] = useState(false)
  const poll = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    try {
      const next = await getTelegram()
      setS(next)
      setError(null)
      return next
    } catch (e) {
      setError(e)
      return null
    }
  }, [])

  const stopPolling = () => {
    if (poll.current) clearInterval(poll.current)
    poll.current = null
    setWaiting(false)
  }

  useEffect(() => {
    if (open) load()
    else stopPolling()
    return stopPolling
  }, [open, load])

  const connect = async () => {
    setBusy(true)
    try {
      const { url } = await linkTelegram()
      window.open(url, "_blank", "noopener")
      setWaiting(true)
      const until = Date.now() + 15 * 60_000
      poll.current = setInterval(async () => {
        const next = await load()
        if (next?.linked) {
          stopPolling()
          toast.success("Telegram connected. Alerts will arrive there.")
        } else if (Date.now() > until) stopPolling()
      }, 3000)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async () => {
    setBusy(true)
    try {
      await unlinkTelegram()
      await load()
      toast.success("Telegram alerts are off")
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const what =
    role === "admin"
      ? ["A new plant is waiting for approval", "A plant goes offline"]
      : ["Your plant is approved, rejected, suspended or resumed", "It comes online, goes offline and back", "A new kit can be downloaded"]

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full border-line p-0 sm:max-w-[440px]">
        <SheetHeader className="px-8 pb-0 pt-8">
          <SheetTitle className="flex items-center gap-2 text-2xl font-medium tracking-[-0.01em]">
            <BellRing className="h-5 w-5" strokeWidth={1.75} /> Telegram alerts
          </SheetTitle>
          <SheetDescription>Short messages with the plant, its state and a link. Never measurements.</SheetDescription>
        </SheetHeader>
        <div className="space-y-6 px-8 py-6">
          {error ? <ApiError error={error} onRetry={load} /> : null}
          {!s ? (
            <Skeleton className="h-24 w-full" />
          ) : !s.configured ? (
            <Notice title="Not set up on this server">
              Telegram alerts need a bot. The ArqauQuat team adds its token (BOT_TOKEN) to the server settings.
            </Notice>
          ) : s.linked ? (
            <>
              <div className="flex items-center justify-between rounded-[12px] bg-paper-warm px-4 py-3">
                <div className="text-sm">
                  <div className="font-medium">{s.telegram_username ? `@${s.telegram_username}` : "Connected"}</div>
                  <div className="fw-num text-xs text-fw-muted">since {fmtDateTime(s.linked_at)}</div>
                </div>
                <StatusPill tone="ok">On</StatusPill>
              </div>
              <Pill variant="outline" loading={busy} onClick={disconnect}>
                Disconnect
              </Pill>
            </>
          ) : (
            <>
              <p className="text-[15px] leading-6 text-fw-muted">
                Opens Telegram with <span className="font-medium text-ink">@{s.bot_username ?? "the ArqauQuat bot"}</span>. Press{" "}
                <span className="font-medium text-ink">Start</span> there and this panel turns on by itself.
              </p>
              <Pill icon={<Send className="h-4 w-4" />} loading={busy} onClick={connect} className="w-full">
                {waiting ? "Waiting for Start in Telegram…" : "Connect Telegram"}
              </Pill>
              {waiting && <p className="text-sm text-fw-muted">The link works once, for 15 minutes.</p>}
            </>
          )}
          <div>
            <div className="fw-label mb-3">You&apos;ll hear when</div>
            <ul className="space-y-2 text-[15px]">
              {what.map((w) => (
                <li key={w} className="flex gap-2">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-fw-accent" aria-hidden />
                  {w}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
