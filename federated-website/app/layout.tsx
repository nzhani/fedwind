import React from "react"
import type { Metadata } from "next"
import localFont from "next/font/local"
import "./globals.css"
import { Navbar } from "@/components/navbar"
import { Footer } from "@/components/footer"
import { Toaster } from "@/components/fw/feedback"
import { AuthProvider } from "@/lib/auth"

// DESIGN_SPEC.md §3.1: an editorial serif for the big moments, a quiet grotesk for everything else.
// Self-hosted (app/fonts, OFL) so builds and the demo work without internet.
const geist = localFont({ src: "./fonts/Geist-Variable.woff2", weight: "100 900", variable: "--font-geist", display: "swap" })
const instrument = localFont({
  src: [
    { path: "./fonts/InstrumentSerif-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/InstrumentSerif-Italic.woff2", weight: "400", style: "italic" },
  ],
  variable: "--font-instrument",
  display: "swap",
})
const fragment = localFont({ src: "./fonts/FragmentMono-Regular.woff2", weight: "400", variable: "--font-fragment", display: "swap" })

export const metadata: Metadata = {
  title: "ArqauQuat · Power forecasts without sharing data",
  description:
    "Plants in Kazakhstan train one wind and solar forecasting model together with federated learning and a frozen GPT-2. Their data never leaves the plant.",
  keywords: ["Federated Learning", "Wind Forecasting", "Solar Forecasting", "LLM", "Privacy", "Renewable Energy", "Kazakhstan"],
  icons: { icon: "/icon.svg" },
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geist.variable} ${instrument.variable} ${fragment.variable}`}>
      <body className="flex min-h-screen flex-col bg-white font-sans text-ink antialiased">
        <AuthProvider>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-20 focus:z-[60] focus:rounded-full focus:bg-ink focus:px-4 focus:py-2 focus:text-white"
          >
            Skip to content
          </a>
          <Navbar />
          <main id="main" className="flex-1">
            {children}
          </main>
          <Footer />
          <Toaster />
        </AuthProvider>
      </body>
    </html>
  )
}
