"use client"

// Telegram alerts panel (account menu): connect with a one-time t.me link, shown as a QR code to scan
// with the phone (or opened on this computer), see the status, disconnect.

import { useCallback, useEffect, useRef, useState } from "react"
import QRCode from "qrcode"
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
  const [link, setLink] = useState<string | null>(null)
  const [qr, setQr] = useState<string | null>(null)
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
    setLink(null)
    setQr(null)
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
      setLink(url)
      // Scan with the phone camera: Telegram opens on the bot, Start links this account
      setQr(await QRCode.toDataURL(url, { width: 440, margin: 1, errorCorrectionLevel: "M",
                                          color: { dark: "#222222", light: "#ffffff" } }))
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
                Shows a QR code for <span className="font-medium text-ink">@{s.bot_username ?? "the ArqauQuat bot"}</span>. Scan it with
                your phone, press <span className="font-medium text-ink">Start</span> in Telegram, and this panel turns on by itself.
              </p>
              {waiting && qr ? (
                <div className="space-y-4">
                  <div className="flex flex-col items-center gap-3 rounded-[12px] bg-paper-warm p-5">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={qr} alt="QR code that opens the ArqauQuat bot in Telegram" className="h-[220px] w-[220px] rounded-[8px]" />
                    <p className="text-center text-sm text-fw-muted">
                      Scan with your phone&apos;s camera, then press <span className="font-medium text-ink">Start</span> in Telegram.
                    </p>
                  </div>
                  <Pill variant="outline" icon={<Send className="h-4 w-4" />} className="w-full"
                        onClick={() => link && window.open(link, "_blank", "noopener")}>
                    Open Telegram on this computer
                  </Pill>
                  <p className="text-sm text-fw-muted">Waiting for Start… The code works once, for 15 minutes.</p>
                </div>
              ) : (
                <Pill icon={<Send className="h-4 w-4" />} loading={busy} onClick={connect} className="w-full">
                  Connect Telegram
                </Pill>
              )}
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
