"use client"

import React from "react"

import { PageLayout, StaggerContainer, StaggerItem } from "@/components/page-layout"
import { SectionHeader } from "@/components/section-header"
import { FeatureCard } from "@/components/feature-card"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Wind,
  Shield,
  Cpu,
  Code,
  Server,
  Lock,
  Eye,
  Users,
  Target,
  Lightbulb,
  Scale,
  Leaf,
  GraduationCap,
} from "lucide-react"

// Technology badge component
function TechBadge({ name, icon: Icon }: { name: string; icon: React.ComponentType<{ className?: string }> }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 shadow-sm">
      <Icon className="h-4 w-4 text-primary" />
      <span className="text-sm font-medium text-foreground">{name}</span>
    </div>
  )
}

export default function AboutPage() {
  return (
    <PageLayout>
      {/* Header */}
      <section className="bg-gradient-to-b from-primary/5 to-background">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <SectionHeader
              badge="About the Project"
              title="FedWind Research Project"
              description="A university research initiative developing privacy-preserving machine learning solutions for renewable energy forecasting."
              centered
            />
          </div>
        </div>
      </section>

      {/* Project Goal Section */}
      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-2 items-center">
          <div>
            <SectionHeader
              badge="Our Mission"
              title="Project Goal & Motivation"
              description="Advancing wind energy forecasting while respecting data privacy and regulatory requirements."
            />

            <div className="mt-6 space-y-4 text-muted-foreground leading-relaxed">
              <p>
                Accurate wind forecasting is crucial for the efficient operation of wind farms and integration of 
                renewable energy into power grids. However, traditional machine learning approaches require 
                centralizing sensitive operational data, creating privacy and competitive concerns.
              </p>
              <p>
                <strong className="text-foreground">FedWind</strong> addresses this challenge by combining 
                Federated Learning with Transformer-based Large Language Models. Our approach enables multiple 
                wind farm operators to collaboratively train a powerful forecasting model while keeping their 
                data completely private and under their control.
              </p>
              <p>
                This research contributes to the broader goal of making renewable energy more predictable and 
                reliable, supporting the global transition to sustainable energy systems.
              </p>
            </div>
          </div>

          <Card className="bg-primary/5 border-primary/20">
            <CardContent className="pt-6">
              <div className="space-y-6">
                <div className="flex items-start gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                    <Target className="h-5 w-5" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground">Primary Objective</h4>
                    <p className="text-sm text-muted-foreground mt-1">
                      Develop a privacy-preserving wind forecasting system that achieves state-of-the-art accuracy 
                      without requiring raw data sharing.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                    <Lightbulb className="h-5 w-5" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground">Research Questions</h4>
                    <ul className="text-sm text-muted-foreground mt-1 space-y-1">
                      <li>Can federated learning match centralized training accuracy?</li>
                      <li>How do Transformers perform on wind time-series data?</li>
                      <li>What privacy guarantees can be achieved?</li>
                    </ul>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/20 text-primary">
                    <Leaf className="h-5 w-5" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground">Impact</h4>
                    <p className="text-sm text-muted-foreground mt-1">
                      Enabling broader collaboration in renewable energy research while respecting 
                      data sovereignty and competitive concerns.
                    </p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Technologies Section */}
      <section className="bg-muted/50 py-12 sm:py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeader
            badge="Tech Stack"
            title="Technologies Used"
            centered
          />

          <StaggerContainer className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <StaggerItem>
              <Card className="h-full">
                <CardHeader>
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
                    <Server className="h-6 w-6 text-primary" />
                  </div>
                  <CardTitle className="mt-4">Federated Learning</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-base">
                    Built on the Flower framework for scalable federated learning. Implements the FedAvg 
                    algorithm for efficient model aggregation across distributed clients.
                  </CardDescription>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <TechBadge name="Flower" icon={Server} />
                    <TechBadge name="FedAvg" icon={Code} />
                  </div>
                </CardContent>
              </Card>
            </StaggerItem>

            <StaggerItem>
              <Card className="h-full">
                <CardHeader>
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent/10">
                    <Cpu className="h-6 w-6 text-accent" />
                  </div>
                  <CardTitle className="mt-4">LLM Architecture</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-base">
                    Transformer-based architecture inspired by GPT and BERT models, adapted for time-series 
                    forecasting with attention mechanisms for temporal patterns.
                  </CardDescription>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <TechBadge name="Transformer" icon={Cpu} />
                    <TechBadge name="Attention" icon={Eye} />
                  </div>
                </CardContent>
              </Card>
            </StaggerItem>

            <StaggerItem>
              <Card className="h-full">
                <CardHeader>
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
                    <Code className="h-6 w-6 text-primary" />
                  </div>
                  <CardTitle className="mt-4">Deep Learning Stack</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-base">
                    Implemented in PyTorch for flexibility and research-friendly development. Supports 
                    GPU acceleration for faster training on local devices.
                  </CardDescription>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <TechBadge name="PyTorch" icon={Code} />
                    <TechBadge name="CUDA" icon={Cpu} />
                  </div>
                </CardContent>
              </Card>
            </StaggerItem>
          </StaggerContainer>

          {/* Additional Tech Details */}
          <div className="mt-10 mx-auto max-w-3xl">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Technical Specifications</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <h4 className="font-medium text-foreground text-sm mb-2">Model Architecture</h4>
                    <ul className="space-y-1 text-sm text-muted-foreground">
                      <li>Multi-head Self-Attention (8 heads)</li>
                      <li>6 Transformer encoder layers</li>
                      <li>Hidden dimension: 512</li>
                      <li>Positional encoding for time</li>
                    </ul>
                  </div>
                  <div>
                    <h4 className="font-medium text-foreground text-sm mb-2">Training Configuration</h4>
                    <ul className="space-y-1 text-sm text-muted-foreground">
                      <li>Local epochs per round: 5</li>
                      <li>Batch size: 32</li>
                      <li>Learning rate: 1e-4 (Adam)</li>
                      <li>Sequence length: 168 hours</li>
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Ethical Focus Section */}
      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <SectionHeader
          badge="Ethics & Privacy"
          title="Our Ethical Commitment"
          centered
        />

        <StaggerContainer className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <StaggerItem>
            <FeatureCard
              icon={<Lock className="h-6 w-6" />}
              title="Data Privacy"
              description="Raw data never leaves client devices. Only mathematical model updates are transmitted to the central server."
            />
          </StaggerItem>

          <StaggerItem>
            <FeatureCard
              icon={<Shield className="h-6 w-6" />}
              title="No Data Leakage"
              description="Model updates are designed to prevent reconstruction of original data through gradient analysis attacks."
            />
          </StaggerItem>

          <StaggerItem>
            <FeatureCard
              icon={<Scale className="h-6 w-6" />}
              title="Regulatory Compliance"
              description="Architecture supports compliance with GDPR, data sovereignty requirements, and industry regulations."
            />
          </StaggerItem>

          <StaggerItem>
            <FeatureCard
              icon={<Users className="h-6 w-6" />}
              title="Fair Collaboration"
              description="All participants benefit equally from the shared model regardless of their individual data contribution size."
            />
          </StaggerItem>
        </StaggerContainer>

        {/* Privacy Guarantee Box */}
        <div className="mt-10 mx-auto max-w-3xl">
          <Card className="border-accent bg-accent/5">
            <CardContent className="pt-6">
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground">
                  <Shield className="h-6 w-6" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground text-lg">Privacy Guarantee</h4>
                  <p className="text-muted-foreground mt-2 leading-relaxed">
                    In federated mode, your wind farm data <strong className="text-foreground">never leaves your infrastructure</strong>. 
                    The central server only receives model weight updates - mathematical values that cannot be reverse-engineered 
                    to reveal your original data. This means competitors cannot access your operational patterns, regulatory 
                    compliance is maintained, and your data sovereignty is fully preserved.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Academic Context */}
      <section className="bg-muted/50 py-12 sm:py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <div className="inline-flex items-center justify-center h-16 w-16 rounded-full bg-primary/10 mb-6">
              <GraduationCap className="h-8 w-8 text-primary" />
            </div>
            <h2 className="text-2xl font-bold text-foreground sm:text-3xl">
              Academic Research Project
            </h2>
            <p className="mt-4 text-muted-foreground leading-relaxed">
              FedWind is developed as part of university research focused on the intersection of privacy-preserving 
              machine learning and renewable energy systems. The project aims to demonstrate that collaborative 
              learning can achieve comparable or superior results to centralized approaches while maintaining 
              strict data privacy guarantees.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-4 text-sm">
              <div className="rounded-lg border border-border bg-card px-4 py-2">
                <span className="text-muted-foreground">Focus Area:</span>{" "}
                <span className="font-medium text-foreground">Federated Learning</span>
              </div>
              <div className="rounded-lg border border-border bg-card px-4 py-2">
                <span className="text-muted-foreground">Domain:</span>{" "}
                <span className="font-medium text-foreground">Renewable Energy</span>
              </div>
              <div className="rounded-lg border border-border bg-card px-4 py-2">
                <span className="text-muted-foreground">Application:</span>{" "}
                <span className="font-medium text-foreground">Time-Series Forecasting</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Future Work */}
      {/* <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <SectionHeader
          badge="Roadmap"
          title="Future Development"
          centered
        />

        <div className="mt-10 mx-auto max-w-2xl">
          <Card>
            <CardContent className="pt-6">
              <ul className="space-y-4">
                {[
                  {
                    title: "Differential Privacy",
                    description: "Adding noise to model updates for mathematical privacy guarantees",
                  },
                  {
                    title: "Secure Aggregation",
                    description: "Cryptographic protocols to hide individual client updates from the server",
                  },
                  {
                    title: "Personalization",
                    description: "Local fine-tuning to adapt the global model to site-specific conditions",
                  },
                  {
                    title: "Real-time Inference",
                    description: "Streaming predictions with continuous model updates",
                  },
                  {
                    title: "Multi-modal Inputs",
                    description: "Incorporating weather forecasts and satellite imagery",
                  },
                ].map((item, idx) => (
                  <li key={idx} className="flex items-start gap-3">
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold">
                      {idx + 1}
                    </div>
                    <div>
                      <h4 className="font-medium text-foreground">{item.title}</h4>
                      <p className="text-sm text-muted-foreground">{item.description}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </section> */}
    </PageLayout>
  )
}
