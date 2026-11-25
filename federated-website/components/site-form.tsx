"use client"

// Site registration form (SITE_NETWORK_PLAN.md §4 step 1): new sites and edits while waiting for approval.
// The API validates everything again (Kazakhstan bounds, equipment per energy type, consents).

import { useState, type FormEvent } from "react"
import { Check, ExternalLink, Sun, Wind } from "lucide-react"
import { Field, FormSection, Input, Segmented, Select, StickyBar, ToggleCard } from "@/components/fw/form"
import { ApiError } from "@/components/fw/feedback"
import { Pill, PillLink } from "@/components/fw/button"
import {
  DATA_SOURCES,
  KZ_BOUNDS,
  KZ_TIMEZONES,
  type EnergyType,
  type SiteDetail,
  type SiteRegistration,
} from "@/lib/platform-api"

type FormState = {
  name: string
  energy_type: EnergyType
  lat: string
  lon: string
  timezone: string
  capacity_mw: string
  data_source: SiteRegistration["data_source"]
  contact: string
  turbine_model: string
  turbine_count: string
  hub_height_m: string
  rated_power_kw: string
  module_type: string
  tilt_deg: string
  azimuth_deg: string
  tracking: "fixed" | "single-axis" | "dual-axis"
  train: boolean
  share_forecast_window: boolean
  public_forecasts: boolean
}

function initialState(site?: SiteDetail): FormState {
  const eq = (site?.equipment ?? {}) as Record<string, unknown>
  const str = (v: unknown) => (v === undefined || v === null ? "" : String(v))
  const consents = (site?.consents ?? {}) as Record<string, unknown>
  return {
    name: site?.name ?? "",
    energy_type: site?.energy_type ?? "wind",
    lat: str(site?.lat),
    lon: str(site?.lon),
    timezone: site?.timezone ?? "Asia/Almaty",
    capacity_mw: site?.capacity_kw ? String(site.capacity_kw / 1000) : "",
    data_source: (site?.data_source as FormState["data_source"]) ?? "csv",
    contact: site?.contact ?? "",
    turbine_model: str(eq.turbine_model),
    turbine_count: str(eq.turbine_count),
    hub_height_m: str(eq.hub_height_m),
    rated_power_kw: str(eq.rated_power_kw),
    module_type: str(eq.module_type),
    tilt_deg: str(eq.tilt_deg),
    azimuth_deg: eq.azimuth_deg === undefined ? "180" : str(eq.azimuth_deg),
    tracking: (eq.tracking as FormState["tracking"]) ?? "fixed",
    train: true, // required to join: the form shows it locked on
    share_forecast_window: Boolean(consents.share_forecast_window),
    public_forecasts: Boolean(consents.public_forecasts),
  }
}

function toRegistration(f: FormState): SiteRegistration {
  const num = (v: string) => Number(v.replace(",", "."))
  return {
    name: f.name.trim(),
    energy_type: f.energy_type,
    lat: num(f.lat),
    lon: num(f.lon),
    timezone: f.timezone,
    capacity_kw: num(f.capacity_mw) * 1000,
    data_source: f.data_source,
    contact: f.contact.trim(),
    equipment:
      f.energy_type === "wind"
        ? {
            turbine_model: f.turbine_model.trim(),
            turbine_count: num(f.turbine_count),
            hub_height_m: num(f.hub_height_m),
            ...(f.rated_power_kw ? { rated_power_kw: num(f.rated_power_kw) } : {}),
          }
        : { module_type: f.module_type.trim(), tilt_deg: num(f.tilt_deg), azimuth_deg: num(f.azimuth_deg), tracking: f.tracking },
    consents: { train: f.train, share_forecast_window: f.share_forecast_window, public_forecasts: f.public_forecasts },
  }
}

export function SiteForm({
  site,
  submitLabel,
  onSubmit,
  cancelHref = "/sites",
}: {
  site?: SiteDetail
  submitLabel: string
  onSubmit: (body: SiteRegistration) => Promise<void>
  cancelHref?: string
}) {
  const [f, setF] = useState<FormState>(() => initialState(site))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((cur) => ({ ...cur, [k]: v }))
  const text = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) => set(k, e.target.value as never)

  const lat = Number(f.lat.replace(",", "."))
  const lon = Number(f.lon.replace(",", "."))
  const located = f.lat !== "" && f.lon !== "" && Number.isFinite(lat) && Number.isFinite(lon)
  const outside = located && (lat < KZ_BOUNDS.lat[0] || lat > KZ_BOUNDS.lat[1] || lon < KZ_BOUNDS.lon[0] || lon > KZ_BOUNDS.lon[1])
  const wind = f.energy_type === "wind"
  const turbineMw = wind && f.turbine_count && f.rated_power_kw ? (Number(f.turbine_count) * Number(f.rated_power_kw.replace(",", "."))) / 1000 : null

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (outside) return
    setBusy(true)
    setError(null)
    try {
      await onSubmit(toRegistration(f))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate={false}>
      <FormSection title="Plant" help="What the federation will call it and how big it is.">
        <Field label="Name" htmlFor="name">
          <Input id="name" required minLength={2} maxLength={100} value={f.name} onChange={text("name")} placeholder="Zhanatas Wind Farm" />
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Type">
            <Segmented
              ariaLabel="Energy type"
              value={f.energy_type}
              onChange={(v) => set("energy_type", v)}
              options={[
                { value: "wind" as EnergyType, label: <><Wind className="h-4 w-4" strokeWidth={1.75} /> Wind</> },
                { value: "solar" as EnergyType, label: <><Sun className="h-4 w-4" strokeWidth={1.75} /> Solar</> },
              ]}
            />
          </Field>
          <Field
            label="Installed capacity"
            htmlFor="capacity"
            help={turbineMw ? `Turbines add up to ${+turbineMw.toFixed(2)} MW` : "Megawatts, AC"}
          >
            <div className="relative">
              <Input id="capacity" mono required inputMode="decimal" value={f.capacity_mw} onChange={text("capacity_mw")} placeholder="100" className="pr-12" />
              <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-sm text-fw-muted">MW</span>
            </div>
          </Field>
        </div>
      </FormSection>

      <FormSection title="Location" help="Coordinates of the plant; forecasts and the simulation use them.">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Latitude" htmlFor="lat" error={outside ? "Outside Kazakhstan" : undefined}>
            <Input id="lat" mono required inputMode="decimal" value={f.lat} onChange={text("lat")} placeholder="43.57" aria-invalid={outside} />
          </Field>
          <Field label="Longitude" htmlFor="lon" error={outside ? "The federation covers plants in Kazakhstan" : undefined}>
            <Input id="lon" mono required inputMode="decimal" value={f.lon} onChange={text("lon")} placeholder="69.75" aria-invalid={outside} />
          </Field>
        </div>
        {located && !outside && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span className="inline-flex items-center gap-1.5 text-ink">
              <Check className="h-4 w-4 text-ok" aria-hidden /> Inside Kazakhstan
            </span>
            <a
              className="inline-flex items-center gap-1 text-fw-muted underline-offset-4 hover:text-ink hover:underline"
              href={`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=11/${lat}/${lon}`}
              target="_blank"
              rel="noreferrer"
            >
              Open in map <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          </div>
        )}
        <Field label="Time zone" htmlFor="tz">
          <Select id="tz" value={f.timezone} onChange={(e) => set("timezone", e.target.value)}>
            {KZ_TIMEZONES.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </Select>
        </Field>
      </FormSection>

      <FormSection title="Equipment" help={wind ? "Turbines turn the forecast wind into power." : "Panels turn the forecast irradiance into power."}>
        {wind ? (
          <>
            <Field label="Turbine model" htmlFor="tm">
              <Input id="tm" required value={f.turbine_model} onChange={text("turbine_model")} placeholder="Goldwind GW 121/2500" />
            </Field>
            <div className="grid gap-5 sm:grid-cols-3">
              <Field label="Number of turbines" htmlFor="tc">
                <Input id="tc" mono required inputMode="numeric" value={f.turbine_count} onChange={text("turbine_count")} placeholder="40" />
              </Field>
              <Field label="Rated power, each" htmlFor="rp" help="kW">
                <Input id="rp" mono inputMode="decimal" value={f.rated_power_kw} onChange={text("rated_power_kw")} placeholder="2500" />
              </Field>
              <Field label="Hub height" htmlFor="hh" help="m">
                <Input id="hh" mono required inputMode="decimal" value={f.hub_height_m} onChange={text("hub_height_m")} placeholder="90" />
              </Field>
            </div>
          </>
        ) : (
          <>
            <Field label="Module type" htmlFor="mt">
              <Input id="mt" required value={f.module_type} onChange={text("module_type")} placeholder="Mono PERC 545 W" />
            </Field>
            <div className="grid gap-5 sm:grid-cols-3">
              <Field label="Mounting" htmlFor="tr">
                <Select id="tr" value={f.tracking} onChange={(e) => set("tracking", e.target.value as FormState["tracking"])}>
                  <option value="fixed">Fixed</option>
                  <option value="single-axis">Single-axis tracking</option>
                  <option value="dual-axis">Dual-axis tracking</option>
                </Select>
              </Field>
              <Field label="Tilt" htmlFor="tilt" help="degrees">
                <Input id="tilt" mono required inputMode="decimal" value={f.tilt_deg} onChange={text("tilt_deg")} placeholder="30" />
              </Field>
              <Field label="Azimuth" htmlFor="az" help="180 = south">
                <Input id="az" mono required inputMode="decimal" value={f.azimuth_deg} onChange={text("azimuth_deg")} placeholder="180" />
              </Field>
            </div>
          </>
        )}
      </FormSection>

      <FormSection title="Data and contact" help="How the plant exports its measurements, and who we talk to.">
        <Field label="Data source" htmlFor="ds">
          <Select id="ds" value={f.data_source} onChange={(e) => set("data_source", e.target.value as FormState["data_source"])}>
            {DATA_SOURCES.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Technical contact" htmlFor="contact" help="Name and email or phone of the person who installs the kit">
          <Input id="contact" required minLength={3} maxLength={200} value={f.contact} onChange={text("contact")} placeholder="Aigerim S., +7 701 000 0000" />
        </Field>
      </FormSection>

      <FormSection title="Consents" help="What the plant agrees to share. You can ask to change these later.">
        <ToggleCard
          title="Federated training"
          description="The plant trains the shared model on its own data and sends only model updates."
          checked
          locked
        />
        <ToggleCard
          title="Central forecasting"
          description="Share the last two weeks of wind speed or irradiance so the ArqauQuat server forecasts for you. Nothing else."
          checked={f.share_forecast_window}
          onChange={(v) => set("share_forecast_window", v)}
        />
        <ToggleCard
          title="Public forecasts"
          description="Anyone can see this plant's forecasts. Off: only your organization and the ArqauQuat team."
          checked={f.public_forecasts}
          onChange={(v) => set("public_forecasts", v)}
        />
      </FormSection>

      <StickyBar note={error ? <ApiError error={error} /> : undefined}>
        <PillLink href={cancelHref} variant="ghost">
          Cancel
        </PillLink>
        <Pill type="submit" loading={busy} disabled={outside} arrow>
          {submitLabel}
        </Pill>
      </StickyBar>
    </form>
  )
}
