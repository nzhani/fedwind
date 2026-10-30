"use client"

import React from "react"

import { PageLayout, StaggerContainer, StaggerItem } from "@/components/page-layout"
import { SectionHeader } from "@/components/section-header"
import {
  Upload,
  Server,
  Download,
  Shield,
  AlertTriangle,
  CheckCircle2,
  Laptop,
  RefreshCw,
  ArrowRight,
  FileText,
  Lock,
  Cloud,
  HardDrive,
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

// Step card component for the instructions
function StepCard({
  step,
  icon,
  title,
  description,
  details,
}: {
  step: number
  icon: React.ReactNode
  title: string
  description: string
  details?: string[]
}) {
  return (
    <div className="relative flex gap-4">
      <div className="flex flex-col items-center">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground font-bold">
          {step}
        </div>
        <div className="mt-2 flex-1 w-px bg-border" />
      </div>
      <div className="pb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            {icon}
          </div>
          <h4 className="font-semibold text-foreground">{title}</h4>
        </div>
        <p className="text-muted-foreground text-sm leading-relaxed">{description}</p>
        {details && details.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {details.map((detail, idx) => (
              <li key={idx} className="flex items-start gap-2 text-sm text-muted-foreground">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-accent mt-0.5" />
                <span>{detail}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// Warning/Note component
function NoteBox({
  type,
  title,
  children,
}: {
  type: "warning" | "info" | "success"
  title: string
  children: React.ReactNode
}) {
  const styles = {
    warning: {
      bg: "bg-amber-50 border-amber-200",
      icon: <AlertTriangle className="h-5 w-5 text-amber-600" />,
      titleColor: "text-amber-800",
      textColor: "text-amber-700",
    },
    info: {
      bg: "bg-primary/5 border-primary/20",
      icon: <Shield className="h-5 w-5 text-primary" />,
      titleColor: "text-primary",
      textColor: "text-foreground/80",
    },
    success: {
      bg: "bg-accent/10 border-accent/20",
      icon: <CheckCircle2 className="h-5 w-5 text-accent" />,
      titleColor: "text-accent",
      textColor: "text-foreground/80",
    },
  }

  const style = styles[type]

  return (
    <div className={`rounded-lg border ${style.bg} p-4`}>
      <div className="flex items-start gap-3">
        {style.icon}
        <div>
          <h4 className={`font-semibold ${style.titleColor}`}>{title}</h4>
          <div className={`mt-1 text-sm ${style.textColor}`}>{children}</div>
        </div>
      </div>
    </div>
  )
}

export default function InstructionsPage() {
  return (
    <PageLayout>
      {/* Header */}
      <section className="bg-gradient-to-b from-primary/5 to-background">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <SectionHeader
              badge="Getting Started"
              title="How to Use FedWind"
              description=""
              centered
            />
          </div>
        </div>
      </section>

      {/* Overview Section */}
      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <Card className="border-primary/20 bg-primary/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              Overview
            </CardTitle>
          </CardHeader>
          <CardContent className="prose prose-sm max-w-none">
            <p className="text-muted-foreground leading-relaxed">
              FedWind allows wind farm operators and researchers to participate in collaborative wind forecasting 
              <strong className="text-foreground"> without sharing their raw data</strong>. The system supports two primary modes of operation:
            </p>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Cloud className="h-5 w-5 text-primary" />
                  <span className="font-semibold text-foreground">Option 1: Server Upload</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Upload your CSV data to our secure server for centralized training. Simpler setup, but data leaves your premises.
                </p>
              </div>
              <div className="rounded-lg border-2 border-accent bg-accent/5 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <HardDrive className="h-5 w-5 text-accent" />
                  <span className="font-semibold text-foreground">Option 2: Federated Mode</span>
                  <span className="rounded-full bg-accent/20 px-2 py-0.5 text-xs font-medium text-accent">Recommended</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Keep your data local. Train on your own device and only share model updates. Maximum privacy.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Two Options */}
      <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <StaggerContainer className="grid gap-8 lg:grid-cols-2">
          {/* Option 1: Upload to Server */}
          <StaggerItem>
            <Card className="h-full">
              <CardHeader className="border-b border-border">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                      <Upload className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle>Option 1: Upload Data to Server</CardTitle>
                      <CardDescription>Centralized training approach</CardDescription>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-6">
                <div className="space-y-0">
                  <StepCard
                    step={1}
                    icon={<FileText className="h-4 w-4" />}
                    title="Prepare Your Data"
                    description="Format your wind data as a CSV file with the required columns."
                    details={[
                      "Timestamp (datetime format)",
                      "Wind speed (m/s)",
                      "Wind direction (degrees)",
                      "Power output (kW) - optional",
                      "Temperature, pressure - optional",
                    ]}
                  />
                  <StepCard
                    step={2}
                    icon={<Upload className="h-4 w-4" />}
                    title="Upload CSV File"
                    description="Use the dashboard to securely upload your prepared CSV file to our server."
                  />
                  <StepCard
                    step={3}
                    icon={<Server className="h-4 w-4" />}
                    title="Preprocessing & Training"
                    description="Our server automatically preprocesses your data and trains the forecasting model."
                    details={[
                      "Data normalization",
                      "Missing value handling",
                      "Feature engineering",
                      "Model training with LLM architecture",
                    ]}
                  />
                  <StepCard
                    step={4}
                    icon={<Download className="h-4 w-4" />}
                    title="Receive Predictions"
                    description="View forecasts directly in the dashboard or download results as CSV."
                  />
                </div>

                <NoteBox type="warning" title="Privacy Consideration">
                  <p>
                    With this option, your raw data is uploaded to our server. While we implement security measures, 
                    consider using <strong>Option 2 (Federated Mode)</strong> if data privacy is critical.
                  </p>
                </NoteBox>
              </CardContent>
            </Card>
          </StaggerItem>

          {/* Option 2: Federated Mode */}
          <StaggerItem>
            <Card className="h-full border-2 border-accent">
              <CardHeader className="border-b border-accent/20 bg-accent/5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                      <Lock className="h-5 w-5" />
                    </div>
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        Option 2: Local Training
                        <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground">
                          Recommended
                        </span>
                      </CardTitle>
                      <CardDescription>Federated Learning approach</CardDescription>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-6">
                <div className="space-y-0">
                  <StepCard
                    step={1}
                    icon={<Download className="h-4 w-4" />}
                    title="Download Global Model"
                    description="Fetch the latest global model from the central server to your local machine."
                  />
                  <StepCard
                    step={2}
                    icon={<FileText className="h-4 w-4" />}
                    title="Load Your Local Data"
                    description="Point the training script to your local CSV file. Data never leaves your device."
                    details={[
                      "Same CSV format as Option 1",
                      "Data stays on your machine",
                      "No network transfer of raw data",
                    ]}
                  />
                  <StepCard
                    step={3}
                    icon={<Laptop className="h-4 w-4" />}
                    title="Configure Training Parameters"
                    description="Choose your model, algorithm, and training settings on the dashboard."
                    details={[
                      "Training Model: GPT4TS, LLaMA, BERT, BART, OPT, Gemma or Qwen",
                      "FL Algorithm: FedAvg, FedProx, SCAFFOLD, StatAvg, FedPer or FedLN",
                      "Prediction Length: 1, 72, or 432 steps",
                      "Number of Clients: 1-10 simulated federated clients",
                      "Communication Rounds: optimized default per prediction length (editable in Advanced)",
                      "Local Epochs per Round: optimized default per prediction length (editable in Advanced)",
                      "Advanced parameters (LLM layers, dropout, LR, batch size, etc.) are pre-filled with best-performing settings",
                    ]}
                  />
                  <StepCard
                    step={4}
                    icon={<Laptop className="h-4 w-4" />}
                    title="Train Locally"
                    description="Run the training script on your machine. The model learns from your data locally."
                    details={[
                      "Training runs on your hardware",
                      "GPU acceleration supported",
                      "Uses your selected algorithm",
                    ]}
                  />
                  <StepCard
                    step={5}
                    icon={<Upload className="h-4 w-4" />}
                    title="Upload Model Updates"
                    description="Send only the model weights/gradients to the server. No raw data is transmitted."
                  />
                  <StepCard
                    step={6}
                    icon={<RefreshCw className="h-4 w-4" />}
                    title="Algorithm Aggregation"
                    description="The server aggregates updates from all participants using your selected federated algorithm."
                  />
                </div>

                <NoteBox type="success" title="Maximum Privacy">
                  <p>
                    Your raw data never leaves your device. Only mathematical model updates (gradients) 
                    are shared. The server and other participants cannot reconstruct your original data.
                  </p>
                </NoteBox>
              </CardContent>
            </Card>
          </StaggerItem>
        </StaggerContainer>
      </section>

    </PageLayout>
  )
}
