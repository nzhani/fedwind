// Split layout for Log in / Register (APP_PAGES_SPEC.md §5): glowing accent panel + centred form.

import type { ReactNode } from "react"
import { BrandMark } from "@/components/fw/mark"

export function AuthSplit({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-[100svh] lg:grid-cols-12">
      <aside className="fw-glow flex min-h-[200px] flex-col justify-between px-6 pb-8 pt-24 text-white lg:col-span-5 lg:min-h-0 lg:px-12 lg:pb-12 lg:pt-28">
        <BrandMark className="hidden h-12 w-12 text-white lg:block" />
        <p className="font-serif text-[40px] leading-[1] tracking-[-0.03em] lg:text-[56px]">
          Forecasts, <em>without sharing</em> data.
        </p>
        <ul className="mt-6 hidden space-y-2 text-lg leading-6 lg:block">
          <li>Train at the plant</li>
          <li>Only model updates travel</li>
          <li>One shared forecast for every site</li>
        </ul>
      </aside>
      <div className="flex items-center justify-center px-5 py-12 lg:col-span-7 lg:px-10 lg:pt-24">
        <div className="w-full max-w-[400px]">{children}</div>
      </div>
    </div>
  )
}
