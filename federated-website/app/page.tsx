"use client"

// Home (DESIGN_SPEC.md §1.1, §7.2): orange hero → two-tone statement → orange "Forecasts" band →
// ink feature stack → federation marquee → FAQ → inset orange call to action.

import { useEffect, useRef, useState } from "react"
import { motion, useReducedMotion, useScroll, useTransform, type MotionValue } from "framer-motion"
import { ChevronDown, Plus, Sun, Wind } from "lucide-react"
import { BrandMark } from "@/components/fw/mark"
import { PillLink } from "@/components/fw/button"
import { useAuth } from "@/lib/auth"
import { FederationMap } from "@/components/federation-map"
import { getSites, type Site } from "@/lib/platform-api"

const FALLBACK_SITES: Pick<Site, "id" | "name" | "energy_type">[] = [
  { id: "almaty", name: "Almaty", energy_type: "wind" },
  { id: "zhezkazgan", name: "Zhezkazgan", energy_type: "wind" },
  { id: "aktau", name: "Aktau", energy_type: "wind" },
  { id: "taraz", name: "Taraz", energy_type: "wind" },
  { id: "aktobe", name: "Aktobe", energy_type: "wind" },
  { id: "konaev", name: "Konaev", energy_type: "solar" },
  { id: "shymkent", name: "Shymkent", energy_type: "solar" },
  { id: "kyzylorda", name: "Kyzylorda", energy_type: "solar" },
  { id: "saran", name: "Saran", energy_type: "solar" },
  { id: "turkistan", name: "Turkistan", energy_type: "solar" },
]

export default function HomePage() {
  const [sites, setSites] = useState<Pick<Site, "id" | "name" | "energy_type">[]>(FALLBACK_SITES)
  const [mapSites, setMapSites] = useState<Site[]>([])
  useEffect(() => {
    getSites()
      .then((all) => {
        // Visitors see lab sites and the plants that chose public forecasts
        const visible = all.filter((s) => s.kind !== "plant" || s.forecast_public)
        if (visible.length) {
          setSites(visible)
          setMapSites(visible)
        }
      })
      .catch(() => undefined)
  }, [])

  return (
    <div className="-mb-px">
      <Hero />
      <Statement siteCount={sites.length} />
      <ForecastBand />
      <FeatureStack />
      <Federation sites={sites} mapSites={mapSites} />
      <Faq />
      <CallToAction />
    </div>
  )
}

// -- 1. hero -----------------------------------------------------------------------------------

function Hero() {
  const reduce = useReducedMotion()
  return (
    <section className="fw-glow relative flex min-h-[100svh] flex-col items-center justify-center px-5 pb-24 pt-32 text-center text-white">
      <motion.div
        initial={reduce ? false : { rotate: -150, scale: 0.4, opacity: 0 }}
        animate={{ rotate: 0, scale: 1, opacity: 1 }}
        transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
      >
        <BrandMark className="h-16 w-16 text-white sm:h-20 sm:w-20" />
      </motion.div>
      <motion.h1
        initial={reduce ? false : { y: 28, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.9, delay: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="fw-display mt-10 max-w-[1120px] text-balance"
      >
        Forecasting wind and sun, <em className="italic">without sharing</em> the data.
      </motion.h1>
      <motion.div
        initial={reduce ? false : { y: 16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.75 }}
        className="mt-10 flex flex-col items-center gap-6"
      >
        <p className="max-w-[640px] text-[22px] leading-[1.4] tracking-[-0.01em] text-white sm:text-2xl">
          Plants across Kazakhstan train one forecasting model together. Their measurements never leave the plant.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <PillLink href="/forecast" variant="onfill" size="l" arrow>
            See forecasts
          </PillLink>
          <PillLink href="/register" variant="ink" size="l">
            Register your plant
          </PillLink>
        </div>
      </motion.div>
      <a href="#statement" aria-label="Scroll to the next section" className="absolute bottom-8 rounded-full p-2 text-white">
        <ChevronDown className="h-6 w-6 motion-safe:animate-bounce" />
      </a>
    </section>
  )
}

// -- 2. statement --------------------------------------------------------------------------------

const STATEMENT: { text: string; accent?: boolean }[] = [
  { text: "Every plant trains the same model on its own data." },
  { text: "Only model updates travel, the measurements never leave the plant,", accent: true },
  { text: "and every site gets power forecasts from the newest shared model." },
]

function Word({ word, progress, range, accent }: { word: string; progress: MotionValue<number>; range: [number, number]; accent?: boolean }) {
  const opacity = useTransform(progress, range, [0.16, 1])
  return (
    <motion.span style={{ opacity }} className={accent ? "text-fw-accent-dark" : "text-ink"}>
      {word}{" "}
    </motion.span>
  )
}

function Statement({ siteCount }: { siteCount: number }) {
  const ref = useRef<HTMLParagraphElement>(null)
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.85", "end 0.5"] })
  const words = STATEMENT.flatMap((part) => part.text.split(" ").map((w) => ({ w, accent: part.accent })))
  return (
    <section id="statement" className="scroll-mt-20 bg-white px-5 py-[120px] sm:px-10">
      <div className="mx-auto max-w-[1080px]">
        <div className="fw-label mb-8">Federated learning</div>
        <p ref={ref} className="fw-heading-l">
          {words.map((x, i) =>
            reduce ? (
              <span key={i} className={x.accent ? "text-fw-accent-dark" : "text-ink"}>
                {x.w}{" "}
              </span>
            ) : (
              <Word key={i} word={x.w} accent={x.accent} progress={scrollYProgress} range={[i / words.length, (i + 1) / words.length]} />
            ),
          )}
        </p>
        <dl className="mt-20 grid gap-10 border-t border-line pt-10 sm:grid-cols-3">
          {[
            { v: String(siteCount), l: "sites in the federation, wind and solar" },
            { v: "0.55 MB", l: "model update per plant per round; the frozen GPT-2 (186 MB) never moves" },
            { v: "0", l: "measurements sent for training. Ever." },
          ].map((s) => (
            <div key={s.l}>
              <dt className="fw-num text-[32px] leading-[38px] tracking-[-0.01em] text-ink">{s.v}</dt>
              <dd className="mt-2 max-w-[260px] text-base leading-6 text-fw-muted">{s.l}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}

// -- 3. "Forecasts" band with a product mock-up ---------------------------------------------------

function ForecastBand() {
  return (
    <section className="relative overflow-hidden bg-fw-accent px-5 pt-20 text-center text-white sm:px-10">
      <div className="mx-auto flex max-w-[1080px] flex-col items-center">
        <div className="text-[12px] font-medium uppercase tracking-[0.12em] text-ink">Introducing</div>
        <h2 className="mt-5 text-[64px] font-normal leading-none tracking-[-0.03em] sm:text-[110px]">Forecasts</h2>
        <p className="mt-6 max-w-[680px] text-2xl leading-[1.4]">
          Power for every plant from the newest shared model: megawatts and share of capacity, one hour to eighteen days ahead.
        </p>
        <PillLink href="/forecast" variant="onfill" size="l" arrow className="mt-9">
          See forecasts
        </PillLink>
      </div>
      <motion.div
        initial={{ y: 80, opacity: 0.6 }}
        whileInView={{ y: 0, opacity: 1 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
        className="mx-auto mt-16 max-w-[1000px]"
      >
        <ProductMock />
      </motion.div>
    </section>
  )
}

function ProductMock() {
  // A drawing of the Forecast page, not a screenshot: actual (ink) then forecast (accent)
  const actual = "M0 118 C30 112 50 96 80 92 S130 70 160 74 S210 96 240 88 S290 52 320 58 S370 80 400 76"
  const forecast = "M400 76 C430 72 450 48 480 44 S530 30 560 40 S610 76 640 70 S690 40 720 46 S770 64 800 58"
  const band = "M400 76 C430 60 450 30 480 26 S530 12 560 22 S610 56 640 52 S690 22 720 28 S770 44 800 38 L800 80 C770 86 750 70 720 66 S670 92 640 90 S590 60 560 58 S510 64 480 62 S430 86 400 76 Z"
  return (
    <div className="rounded-t-[20px] bg-white p-5 text-left text-ink shadow-[0_-20px_60px_rgba(120,20,0,0.25)] sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="fw-label">Forecast · wind</div>
          <div className="mt-1 text-xl font-medium tracking-[-0.01em] sm:text-2xl">Zhanatas Wind Farm</div>
        </div>
        <div className="flex gap-2">
          <span className="inline-flex h-[22px] items-center gap-1.5 rounded-full bg-surface px-2.5 text-xs font-medium">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" />
            Online
          </span>
        </div>
      </div>
      <div className="mt-6 grid grid-cols-3 gap-4 border-y border-line py-4">
        {[
          ["Next hour", "38.4 MW"],
          ["Peak, 72 h", "71.2 MW"],
          ["Capacity", "100 MW"],
        ].map(([l, v]) => (
          <div key={l}>
            <div className="fw-label">{l}</div>
            <div className="fw-num mt-1 text-lg sm:text-2xl">{v}</div>
          </div>
        ))}
      </div>
      <svg viewBox="0 0 800 140" className="mt-6 h-auto w-full" aria-hidden>
        {[30, 70, 110].map((y) => (
          <line key={y} x1="0" x2="800" y1={y} y2={y} stroke="rgba(34,34,34,0.06)" />
        ))}
        <path d={band} fill="rgba(255,63,16,0.1)" />
        <path d={actual} fill="none" stroke="#222" strokeWidth="2" />
        <path d={forecast} fill="none" stroke="#ff3f10" strokeWidth="2.5" />
        <line x1="400" x2="400" y1="0" y2="140" stroke="#222" strokeDasharray="3 4" strokeOpacity="0.5" />
        <text x="408" y="14" fontSize="11" fill="#737373" fontFamily="var(--font-mono)">
          now
        </text>
      </svg>
      <div className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-[12px] bg-paper-warm px-4 py-3 text-sm">
        <span className="font-medium">Global wind model</span>
        <span className="text-fw-muted">· run wind-fedavg-h72 · 5 sites · 3 rounds · promoted 2 min ago by Admin</span>
      </div>
    </div>
  )
}

// -- 4. ink feature stack -----------------------------------------------------------------------

const FEATURES = [
  {
    n: "01",
    title: "Train at the plant",
    accent: false,
    points: [
      ["Runs next to the data", "Each plant fine-tunes a small adapter on its own measurements, on its own computer."],
      ["Frozen GPT-2 + LoRA", "The language model stays frozen; only a few million adapter weights learn wind and sun."],
    ],
  },
  {
    n: "02",
    title: "Only model updates travel",
    accent: true,
    points: [
      ["Weights, not data", "After each round a plant sends its adapter update. The server averages them into one model."],
      ["Approved plants only", "A plant joins with a one-time kit from the website and a key the ArqauQuat team can revoke."],
    ],
  },
  {
    n: "03",
    title: "One shared model forecasts every site",
    accent: false,
    points: [
      ["Power from day one", "A new plant gets forecasts in megawatts on the day it connects, before it trains at all."],
      ["Always the newest model", "When the federation trains a better model, every forecast switches to it."],
    ],
  },
]

function FeatureStack() {
  return (
    <section className="bg-ink px-5 py-[120px] text-white sm:px-10">
      <div className="mx-auto max-w-[1200px]">
        <div className="mb-16 max-w-[900px]">
          <div className="mb-6 text-[12px] font-medium uppercase tracking-[0.12em] text-white/70">How it works</div>
          <h2 className="fw-heading-xl">
            Three steps, <span className="text-fw-accent">no data sharing.</span>
          </h2>
        </div>
        <div className="space-y-6">
          {FEATURES.map((f, i) => (
            <article
              key={f.n}
              style={{ top: `${96 + i * 28}px` }}
              className="sticky grid min-h-[400px] gap-10 rounded-[16px] border border-white/10 bg-[#2a2a2a] p-8 sm:p-12 md:grid-cols-2"
            >
              <div className="flex flex-col justify-between gap-8">
                <span className="fw-num text-sm text-fw-accent">{f.n}</span>
                <h3 className={`fw-heading-xl ${f.accent ? "text-fw-accent" : "text-white"}`}>{f.title}</h3>
              </div>
              <div className="flex flex-col justify-end gap-8">
                {f.points.map(([t, b]) => (
                  <div key={t}>
                    <div className="text-2xl font-medium leading-[1.1] sm:text-[32px]">{t}</div>
                    <p className="mt-3 max-w-[460px] text-lg leading-[1.4] text-white/75 sm:text-xl">{b}</p>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

// -- 5. the federation (marquee) ------------------------------------------------------------------

function Federation({ sites, mapSites }: { sites: Pick<Site, "id" | "name" | "energy_type">[]; mapSites: Site[] }) {
  const row = [...sites, ...sites]
  return (
    <section className="overflow-hidden bg-white py-[120px]">
      <div className="mx-auto mb-14 max-w-[1280px] px-5 sm:px-10">
        <div className="fw-label mb-4">The federation</div>
        <h2 className="fw-heading-l max-w-[760px]">Wind and solar sites across Kazakhstan, one shared model.</h2>
        {mapSites.length > 0 && (
          <FederationMap
            sites={mapSites}
            className="mx-auto mt-14 max-w-[1100px]"
            hrefFor={(s) => `/forecast?energy=${s.energy_type}&site=${encodeURIComponent(s.id)}&horizon=72`}
          />
        )}
      </div>
      <div className="group relative" aria-label="Sites in the federation">
        <ul className="flex w-max gap-4 motion-safe:animate-marquee group-hover:[animation-play-state:paused]">
          {row.map((s, i) => (
            <li
              key={`${s.id}-${i}`}
              aria-hidden={i >= sites.length}
              className="flex h-[112px] w-[260px] shrink-0 flex-col justify-between rounded-[16px] bg-paper-warm p-5"
            >
              {s.energy_type === "solar" ? <Sun className="h-6 w-6" strokeWidth={1.5} /> : <Wind className="h-6 w-6" strokeWidth={1.5} />}
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-xl font-medium tracking-[-0.01em]">{s.name}</span>
                <span className="text-sm capitalize text-fw-muted">{s.energy_type}</span>
              </div>
            </li>
          ))}
        </ul>
        <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-white sm:w-40" />
        <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-white sm:w-40" />
      </div>
    </section>
  )
}

// -- 6. FAQ ----------------------------------------------------------------------------------------

const FAQ = [
  [
    "What is federated learning?",
    "A way to train one model across many owners without collecting their data. Each plant trains on its own measurements and sends back only the change to the model; the server averages those changes into a new shared model.",
  ],
  [
    "Does my data leave the plant?",
    "Not for training. The site kit sends a heartbeat with counts (rows, gaps) and, only if you allow central forecasting, the last two weeks of wind speed or irradiance so the server can forecast for you.",
  ],
  [
    "What does a plant install?",
    "A small container from the site kit you download after approval. It enrolls with a one-time token, then reports its status every 30 seconds. An admin can suspend or revoke it at any time.",
  ],
  [
    "How accurate is it?",
    "Every forecast shows the model behind it and its skill against persistence. Today's models are small demo runs on a CPU; the full GPU runs come next.",
  ],
]

function Faq() {
  return (
    <section className="bg-white px-5 pb-[120px] sm:px-10">
      <div className="mx-auto grid max-w-[1200px] gap-12 md:grid-cols-[1fr_1.4fr]">
        <h2 className="text-[32px] font-medium leading-[1.1] tracking-[-0.01em] sm:text-[44px]">Questions</h2>
        <div className="divide-y divide-line border-y border-line">
          {FAQ.map(([q, a]) => (
            <details key={q} className="group py-6">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-6 text-xl font-medium leading-7 tracking-[-0.01em] [&::-webkit-details-marker]:hidden">
                {q}
                <Plus className="h-5 w-5 shrink-0 transition-transform duration-300 group-open:rotate-45" aria-hidden />
              </summary>
              <p className="mt-4 max-w-[640px] text-lg leading-[1.45] text-fw-muted">{a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}

// -- 7. inset call to action ---------------------------------------------------------------------

function CallToAction() {
  const { user } = useAuth()
  const href = user?.role === "operator" ? "/sites/new" : user ? "/sites" : "/register"
  return (
    <section className="bg-white px-3 sm:px-10">
      <div className="fw-glow flex flex-col items-center rounded-[24px] px-6 py-28 text-center text-white sm:py-[150px]">
        <h2 className="fw-display max-w-[900px] text-[56px] sm:text-[88px]">Run a plant in Kazakhstan?</h2>
        <p className="mt-8 max-w-[560px] text-2xl leading-[1.4]">
          Register it, get approved, install the kit. Forecasts arrive the same day; your data stays with you.
        </p>
        <PillLink href={href} variant="onfill" size="l" arrow className="mt-10">
          Register your plant
        </PillLink>
      </div>
    </section>
  )
}
