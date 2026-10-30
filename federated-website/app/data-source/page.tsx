"use client"

import React from "react"

import { PageLayout, StaggerContainer, StaggerItem } from "@/components/page-layout"
import { SectionHeader } from "@/components/section-header"
import {
  Database,
  Globe,
  Shield,
  AlertCircle,
  Compass,
  FlaskConical,
  FileQuestion,
  Layers,
  Lock,
  Settings,
  Sparkles,
  Wind,
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

// Info box component for notes and highlights
function InfoBox({
  type,
  title,
  children,
}: {
  type: "note" | "research" | "privacy"
  title: string
  children: React.ReactNode
}) {
  const styles = {
    note: {
      bg: "bg-amber-50 border-amber-200",
      icon: <AlertCircle className="h-5 w-5 text-amber-600" />,
      titleColor: "text-amber-800",
      textColor: "text-amber-700",
    },
    research: {
      bg: "bg-primary/5 border-primary/20",
      icon: <FlaskConical className="h-5 w-5 text-primary" />,
      titleColor: "text-primary",
      textColor: "text-foreground/80",
    },
    privacy: {
      bg: "bg-accent/10 border-accent/20",
      icon: <Shield className="h-5 w-5 text-accent" />,
      titleColor: "text-accent",
      textColor: "text-foreground/80",
    },
  }

  const style = styles[type]

  return (
    <div className={`rounded-lg border p-4 ${style.bg}`}>
      <div className="flex items-center gap-2 mb-2">
        {style.icon}
        <h4 className={`font-semibold ${style.titleColor}`}>{title}</h4>
      </div>
      <div className={`text-sm leading-relaxed ${style.textColor}`}>{children}</div>
    </div>
  )
}

export default function DataSourcePage() {
  return (
    <PageLayout>
      {/* Hero Section */}
      <section className="relative overflow-hidden bg-gradient-to-b from-primary/5 via-background to-background py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <StaggerContainer>
              <StaggerItem>
                <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary">
                  <Database className="h-4 w-4" />
                  Data Source Information
                </div>
              </StaggerItem>
              <StaggerItem>
                <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl lg:text-5xl text-balance">
                  Data Source & Requirements
                </h1>
              </StaggerItem>
              <StaggerItem>
                <p className="mt-6 text-lg leading-relaxed text-muted-foreground text-pretty">
                  Understanding the data foundation of our federated wind forecasting system, 
                  with an emphasis on flexibility and ongoing research into optimal data formats.
                </p>
              </StaggerItem>
            </StaggerContainer>
          </div>
        </div>
      </section>

      {/* NASA POWER Section */}
      <section className="py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeader
            badge="Primary Data Source"
            title="NASA POWER"
            description=""
          />

          <div className="mt-12 grid gap-8 lg:grid-cols-2">
            <StaggerContainer>
              <StaggerItem>
                <Card className="h-full border-border/50 shadow-sm">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                        <Globe className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <CardTitle className="text-lg">About NASA POWER</CardTitle>
                        <CardDescription>Global meteorological resource</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      The NASA POWER (Prediction of Worldwide Energy Resources) project provides 
                      solar and meteorological data sets from NASA research for support of renewable 
                      energy, sustainable buildings, and agricultural needs.
                    </p>
                    <ul className="space-y-2 text-sm text-muted-foreground">
                      <li className="flex items-start gap-2">
                        <Compass className="h-4 w-4 shrink-0 text-primary mt-0.5" />
                        <span>Global coverage with high spatial resolution</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <Wind className="h-4 w-4 shrink-0 text-primary mt-0.5" />
                        <span>Wind speed and related meteorological parameters</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <Layers className="h-4 w-4 shrink-0 text-primary mt-0.5" />
                        <span>Historical data spanning multiple decades</span>
                      </li>
                    </ul>
                  </CardContent>
                </Card>
              </StaggerItem>
            </StaggerContainer>

            <StaggerContainer>
              <StaggerItem>
                <Card className="h-full border-border/50 shadow-sm">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10">
                        <Sparkles className="h-5 w-5 text-accent" />
                      </div>
                      <div>
                        <CardTitle className="text-lg">Why NASA POWER?</CardTitle>
                        <CardDescription>Research-grade data quality</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      NASA POWER data is particularly well-suited for wind energy research due to 
                      its reliability, accessibility, and comprehensive coverage of relevant 
                      atmospheric parameters.
                    </p>
                    <ul className="space-y-2 text-sm text-muted-foreground">
                      <li className="flex items-start gap-2">
                        <Shield className="h-4 w-4 shrink-0 text-accent mt-0.5" />
                        <span>Publicly available and free for research use</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <Database className="h-4 w-4 shrink-0 text-accent mt-0.5" />
                        <span>Consistent data quality and validation processes</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <Settings className="h-4 w-4 shrink-0 text-accent mt-0.5" />
                        <span>API access for programmatic data retrieval</span>
                      </li>
                    </ul>
                  </CardContent>
                </Card>
              </StaggerItem>
            </StaggerContainer>
          </div>

          {/* External Link */}
          <div className="mt-8 text-center">
            <a 
              href="https://power.larc.nasa.gov/" 
              target="_blank" 
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-sm text-primary hover:text-primary/80 transition-colors"
            >
              <Globe className="h-4 w-4" />
              Visit NASA POWER Portal
              <span className="sr-only">(opens in new tab)</span>
            </a>
          </div>
        </div>
      </section>

      {/* How to Get Data Section */}
      <section className="py-16 sm:py-20 bg-muted/30">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeader
            badge="Step-by-Step Guide"
            title="How to Download Wind Data from NASA POWER"
            description=""
          />

          <div className="mt-12 max-w-5xl mx-auto space-y-8">
            {/* Important Note */}
            {/* <StaggerContainer>
              <StaggerItem>
                <InfoBox type="note" title="Data Preparation Required">
                  <p className="mb-2">
                    After downloading from NASA POWER, you will need to <strong>remove header lines and metadata</strong> from the CSV file, 
                    keeping only the column headers and data rows.
                  </p>
                  <p className="text-xs mt-2 font-mono bg-amber-100/50 p-2 rounded">
                    Expected format: YEAR,MO,DY,HR,WS50M (with data rows below)
                  </p>
                </InfoBox>
              </StaggerItem>
            </StaggerContainer> */}

            {/* Step 1 */}
            <StaggerContainer>
              <StaggerItem>
                <Card className="border-border/50 shadow-sm">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground font-bold">
                        1
                      </div>
                      <div>
                        <CardTitle className="text-lg">Open NASA POWER Data Access Viewer</CardTitle>
                        <CardDescription>Navigate to the data portal</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      Visit the{" "}
                      <a 
                        href="https://power.larc.nasa.gov/data-access-viewer/" 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="text-primary hover:underline"
                      >
                        NASA POWER Data Access Viewer
                      </a>{" "}
                      to begin your data request.
                    </p>
                  </CardContent>
                </Card>
              </StaggerItem>
            </StaggerContainer>

            {/* Step 2 */}
            <StaggerContainer>
              <StaggerItem>
                <Card className="border-border/50 shadow-sm">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground font-bold">
                        2
                      </div>
                      <div>
                        <CardTitle className="text-lg">Configure Your Data Request</CardTitle>
                        <CardDescription>Set up location and resolution parameters</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="space-y-4">
                      <div className="grid gap-4 sm:grid-cols-2">
                        <div className="rounded-lg border border-border bg-muted/30 p-4">
                          <h4 className="font-semibold text-sm text-foreground mb-2">Select Single Point</h4>
                          <p className="text-xs text-muted-foreground">
                            Choose "Single Point" mode to specify a precise location
                          </p>
                        </div>
                        <div className="rounded-lg border border-border bg-muted/30 p-4">
                          <h4 className="font-semibold text-sm text-foreground mb-2">Standard Resolution</h4>
                          <p className="text-xs text-muted-foreground">
                            Select "Standard Resolution" capability
                          </p>
                        </div>
                        <div className="rounded-lg border border-border bg-muted/30 p-4">
                          <h4 className="font-semibold text-sm text-foreground mb-2">Renewable Energy</h4>
                          <p className="text-xs text-muted-foreground">
                            Choose "Renewable Energy" as your user community
                          </p>
                        </div>
                        <div className="rounded-lg border border-border bg-muted/30 p-4">
                          <h4 className="font-semibold text-sm text-foreground mb-2">Hourly Data</h4>
                          <p className="text-xs text-muted-foreground">
                            Select "Hourly" as the temporal level
                          </p>
                        </div>
                      </div>

                      {/* Example Image 1 */}
                      <div className="space-y-3">
                        <img 
                          src="example 1.png"
                          alt="NASA POWER interface showing Single Point selection, Standard Resolution, Renewable Energy community, and Hourly temporal level configuration"
                          className="w-full rounded-lg border border-border shadow-md"
                        />
                        {/* <p className="text-xs text-center text-muted-foreground italic">
                          Example: Configuring data request with Single Point, Standard Resolution, Renewable Energy, and Hourly settings
                        </p> */}
                      </div>
                    </div>

                    <InfoBox type="note" title="Location Depends on Your Project">
                      <p>
                        Enter the <strong>Latitude and Longitude</strong> for your specific location of interest. 
                        You can click on the map or manually enter coordinates. The location should match 
                        the wind farm or area you want to forecast.
                      </p>
                    </InfoBox>
                  </CardContent>
                </Card>
              </StaggerItem>
            </StaggerContainer>

            {/* Step 3 */}
            <StaggerContainer>
              <StaggerItem>
                <Card className="border-border/50 shadow-sm">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground font-bold">
                        3
                      </div>
                      <div>
                        <CardTitle className="text-lg">Set Time Range</CardTitle>
                        <CardDescription>Define your date range</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      Select your desired time extent. The time span selection includes all hours. 
                      Choose dates that cover the period you need for training and testing your forecasting model.
                    </p>
                    <div className="rounded-lg border border-border bg-muted/30 p-4">
                      <p className="text-xs text-muted-foreground">
                        <strong>Recommendation:</strong> Start with 1-2 years of historical data for initial model training.
                      </p>
                    </div>
                  </CardContent>
                </Card>
              </StaggerItem>
            </StaggerContainer>

            {/* Step 4 */}
            <StaggerContainer>
              <StaggerItem>
                <Card className="border-border/50 shadow-sm">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground font-bold">
                        4
                      </div>
                      <div>
                        <CardTitle className="text-lg">Select Parameters and Export Format</CardTitle>
                        <CardDescription>Choose wind data and CSV format</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="space-y-4">
                      <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
                        <h4 className="font-semibold text-sm text-foreground mb-2">Required Parameter</h4>
                        <p className="text-sm text-muted-foreground">
                          Under "Wind/Pressure" section, select:
                        </p>
                        <p className="text-sm font-medium text-primary mt-2">
                          ✓ Wind Speed at 50 Meters (WS50M)
                        </p>
                      </div>

                      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                        <h4 className="font-semibold text-sm text-amber-800 mb-2">Export Format</h4>
                        <p className="text-sm text-amber-700">
                          In the "Data Download" section, select <strong>CSV</strong> format from the dropdown menu.
                        </p>
                      </div>

                      {/* Example Image 2 */}
                      <div className="space-y-3">
                        <img 
                          src="example 2.png"
                          alt="NASA POWER interface showing Wind Speed at 10 Meters parameter selection and CSV format selection with Submit button"
                          className="w-full rounded-lg border border-border shadow-md"
                        />
                      </div>
                    </div>
{/* 
                    <InfoBox type="note" title="Parameter Flexibility">
                      <p>
                        While we recommend <strong>Wind Speed at 10 Meters (WS50M)</strong> as the primary parameter, 
                        you may add additional meteorological variables depending on your forecasting requirements. 
                        Additional parameters may improve model accuracy but are optional.
                      </p>
                    </InfoBox> */}
                  </CardContent>
                </Card>
              </StaggerItem>
            </StaggerContainer>

            {/* Step 5 */}
            <StaggerContainer>
              <StaggerItem>
                <Card className="border-border/50 shadow-sm">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground font-bold">
                        5
                      </div>
                      <div>
                        <CardTitle className="text-lg">Submit and Download</CardTitle>
                        <CardDescription>Get your CSV file</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      Click the <strong>Submit</strong> button. NASA POWER will process your request and 
                      provide a CSV file for download.
                    </p>
                  </CardContent>
                </Card>
              </StaggerItem>
            </StaggerContainer>

            {/* Step 6 - Data Preparation */}
            <StaggerContainer>
              <StaggerItem>
                <Card className="border-accent/30 shadow-sm bg-accent/5">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground font-bold">
                        6
                      </div>
                      <div>
                        <CardTitle className="text-lg">Prepare Your CSV File</CardTitle>
                        <CardDescription className="text-accent/80">Important: Clean the downloaded file</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      The downloaded CSV file will contain NASA POWER metadata and header information. 
                      <strong> You must remove all header lines and metadata</strong>, keeping only the column 
                      names and data rows.
                    </p>

                    <div className="rounded-lg border border-accent/30 bg-background p-4 space-y-3">
                      <h4 className="font-semibold text-sm text-foreground">Expected Final Format:</h4>
                      <pre className="text-xs font-mono bg-muted p-3 rounded overflow-x-auto text-foreground">
{`YEAR,MO,DY,HR,WS50M
2026,1,1,0,8.65
2026,1,1,1,8.42
2026,1,1,2,7.55
2026,1,1,3,6.88
2026,1,1,4,6.68
...`}
                      </pre>
                      <p className="text-xs text-muted-foreground">
                        Remove all NASA POWER header lines, keeping only the column headers and hourly data rows.
                      </p>
                    </div>

                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                      <h4 className="font-semibold text-sm text-amber-800 mb-2">What to Remove</h4>
                      <ul className="text-xs text-amber-700 space-y-1">
                        <li>• NASA POWER project information</li>
                        <li>• Location metadata lines</li>
                        <li>• Parameter descriptions</li>
                        <li>• Any text before the column headers</li>
                      </ul>
                    </div>
                  </CardContent>
                </Card>
              </StaggerItem>
            </StaggerContainer>

            {/* Final Note */}
            <StaggerContainer>
              <StaggerItem>
                <InfoBox type="research" title="Data Format Flexibility">
                  <p>
                    While the example shows the recommended format (YEAR, MO, DY, HR, WS50M), our system 
                    is designed to be flexible. As part of our ongoing research, we are investigating 
                    various data formats and preprocessing approaches. The key requirement is clean, 
                    structured time-series data with wind speed measurements.
                  </p>
                </InfoBox>
              </StaggerItem>
            </StaggerContainer>
          </div>
        </div>
      </section>

      {/* Privacy Section */}
      {/* <section className="py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeader
            badge="Core Principle"
            title="Privacy & Data Sovereignty"
            description=""
          />

          <div className="mt-12 grid gap-6 md:grid-cols-3">
            <StaggerContainer className="contents">
              <StaggerItem>
                <Card className="h-full border-border/50 shadow-sm text-center">
                  <CardContent className="pt-6">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 mb-4">
                      <Lock className="h-6 w-6 text-accent" />
                    </div>
                    <h3 className="font-semibold text-foreground mb-2">Data Stays Local</h3>
                    <p className="text-sm text-muted-foreground">
                      In federated mode, your raw data never leaves your infrastructure. 
                      Only model updates are shared.
                    </p>
                  </CardContent>
                </Card>
              </StaggerItem>

              <StaggerItem>
                <Card className="h-full border-border/50 shadow-sm text-center">
                  <CardContent className="pt-6">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 mb-4">
                      <Shield className="h-6 w-6 text-primary" />
                    </div>
                    <h3 className="font-semibold text-foreground mb-2">Regulatory Compliance</h3>
                    <p className="text-sm text-muted-foreground">
                      Designed to support compliance with data protection regulations 
                      and organizational policies.
                    </p>
                  </CardContent>
                </Card>
              </StaggerItem>

              <StaggerItem>
                <Card className="h-full border-border/50 shadow-sm text-center">
                  <CardContent className="pt-6">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 mb-4">
                      <Settings className="h-6 w-6 text-accent" />
                    </div>
                    <h3 className="font-semibold text-foreground mb-2">Configurable Participation</h3>
                    <p className="text-sm text-muted-foreground">
                      Participants maintain control over their involvement level 
                      and data handling preferences.
                    </p>
                  </CardContent>
                </Card>
              </StaggerItem>
            </StaggerContainer>
          </div>

          <div className="mt-12 max-w-2xl mx-auto">
            <InfoBox type="privacy" title="Privacy-First Research">
              <p>
                Our federated learning approach ensures that the collaborative benefits of 
                multi-site model training can be achieved without compromising the privacy 
                or proprietary nature of individual datasets. This is particularly important 
                for wind farm operators and energy companies with sensitive operational data.
              </p>
            </InfoBox>
          </div>
        </div>
      </section> */}

      {/* Contact Section */}
      <section className="py-16 sm:py-20 bg-muted/30">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <StaggerContainer>
              <StaggerItem>
                <h2 className="text-2xl font-bold text-foreground sm:text-3xl">
                  Questions About Data Requirements?
                </h2>
              </StaggerItem>
              <StaggerItem>
                <p className="mt-4 text-muted-foreground leading-relaxed">
                  As this is an active research project, data format specifications may evolve. 
                  If you are interested in participating or have questions about data compatibility, 
                  please reach out to our research team for the most current information.
                </p>
              </StaggerItem>
              <StaggerItem>
                <p className="mt-6 text-sm text-muted-foreground">
                  We welcome collaboration and feedback from wind energy researchers, 
                  data scientists, and industry practitioners.
                </p>
              </StaggerItem>
            </StaggerContainer>
          </div>
        </div>
      </section>
    </PageLayout>
  )
}
