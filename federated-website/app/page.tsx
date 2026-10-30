"use client"

import Link from "next/link"
import { PageLayout, StaggerContainer, StaggerItem } from "@/components/page-layout"
import { SectionHeader } from "@/components/section-header"
import { FeatureCard } from "@/components/feature-card"
import { Button } from "@/components/ui/button"
import {
  Wind,
  Shield,
  Share2,
  BarChart3,
  ArrowRight,
  Lock,
  Cpu,
  TrendingUp,
} from "lucide-react"

export default function HomePage() {
  return (
    <PageLayout>
      {/* Hero Section */}
      <section className="relative overflow-hidden bg-gradient-to-b from-primary/5 via-background to-background">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8 lg:py-32">
          <StaggerContainer className="mx-auto max-w-4xl text-center">
            <StaggerItem>
              <span className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary">
                <Wind className="h-4 w-4" />
                University Research Project
              </span>
            </StaggerItem>

            <StaggerItem>
              <h1 className="mt-6 text-3xl font-bold tracking-tight text-foreground sm:text-4xl lg:text-5xl text-balance">
                Privacy-Preserving Wind Speed and Power Forecasting using Federated Learning and LLMs
              </h1>
            </StaggerItem>

            <StaggerItem>
              <p className="mt-6 text-lg text-muted-foreground leading-relaxed text-pretty">
                A collaborative approach to accurate wind forecasting that protects data privacy. 
                Multiple wind farms can train a shared model without exposing their sensitive operational data.
              </p>
            </StaggerItem>

            <StaggerItem>
              <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/instructions">
                    View Instructions
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg" className="gap-2 bg-transparent">
                  <Link href="/architecture">
                    Explore System Architecture
                  </Link>
                </Button>
              </div>
            </StaggerItem>
          </StaggerContainer>
        </div>

        {/* Decorative element */}
        <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-border to-transparent" />
      </section>

      {/* Problem Statement Section */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-16 items-center">
          <div>
            <SectionHeader
              badge="The Challenge"
              title="Centralized Training vs. Data Privacy"
              description="Traditional machine learning approaches require centralizing all data in one location, creating significant privacy and regulatory challenges for wind farm operators."
            />
            <div className="mt-6 space-y-4">
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                  <span className="text-xs font-bold">!</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Sensitive operational data cannot be shared due to competitive and regulatory constraints
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                  <span className="text-xs font-bold">!</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Data sovereignty requirements prevent cross-border data transfers
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                  <span className="text-xs font-bold">!</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Individual datasets are often too small for effective deep learning
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-card p-8 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                <Shield className="h-5 w-5" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">Our Solution</h3>
            </div>
            <p className="text-muted-foreground leading-relaxed mb-6">
              Federated Learning enables collaborative model training while keeping all raw data on local devices. 
              Combined with Transformer-based LLMs, our system achieves state-of-the-art forecasting accuracy 
              without compromising data privacy.
            </p>
            <div className="flex items-center gap-2 text-sm text-primary font-medium">
              <Lock className="h-4 w-4" />
              Data never leaves your premises
            </div>
          </div>
        </div>
      </section>

      {/* Key Benefits Section */}
      <section className="bg-muted/50 py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeader
            badge="Key Benefits"
            title="Why Choose FedWind?"
            centered
          />

          <StaggerContainer className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <StaggerItem>
              <FeatureCard
                icon={<Lock className="h-6 w-6" />}
                title="No Raw Data Sharing"
                description="Your operational data stays on your servers. Only model updates (gradients) are shared with the central server, ensuring complete data privacy."
              />
            </StaggerItem>

            <StaggerItem>
              <FeatureCard
                icon={<Share2 className="h-6 w-6" />}
                title="Federated Model Training"
                description="Using the FedAvg algorithm, multiple clients collaboratively train a shared model. Each round aggregates local updates into an improved global model."
              />
            </StaggerItem>

            <StaggerItem>
              <FeatureCard
                icon={<BarChart3 className="h-6 w-6" />}
                title="Multi-Horizon Forecasting"
                description="Predict wind speed and power output across multiple time horizons - from short-term (1-6 hours) to medium-term (24-72 hours) forecasts."
              />
            </StaggerItem>

            <StaggerItem>
              <FeatureCard
                icon={<Cpu className="h-6 w-6" />}
                title="LLM-Powered Predictions"
                description="Transformer-based architecture captures complex temporal patterns and dependencies in wind data for superior forecasting accuracy."
              />
            </StaggerItem>

            <StaggerItem>
              <FeatureCard
                icon={<Shield className="h-6 w-6" />}
                title="Regulatory Compliance"
                description="Meet data protection regulations (GDPR, industry standards) by keeping sensitive data within your jurisdiction and control."
              />
            </StaggerItem>

            <StaggerItem>
              <FeatureCard
                icon={<TrendingUp className="h-6 w-6" />}
                title="Improved Model Quality"
                description="Benefit from diverse training data across multiple wind farms without compromising privacy, leading to more robust and generalizable models."
              />
            </StaggerItem>
          </StaggerContainer>
        </div>
      </section>

      {/* CTA Section */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <div className="rounded-2xl bg-primary p-8 text-center sm:p-12">
          <h2 className="text-2xl font-bold text-primary-foreground sm:text-3xl text-balance">
            Ready to Explore the System?
          </h2>
          <p className="mt-4 text-primary-foreground/80 max-w-2xl mx-auto">
            Learn how to participate in federated wind forecasting or try our interactive dashboard demo.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Button asChild size="lg" variant="secondary" className="gap-2">
              <Link href="/instructions">
                Get Started
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="gap-2 border-primary-foreground/20 text-primary-foreground hover:bg-primary-foreground/10 bg-transparent">
              <Link href="/dashboard">
                Try Dashboard Demo
              </Link>
            </Button>
          </div>
        </div>
      </section>
    </PageLayout>
  )
}
