"use client"

import React from "react"
import { TrendingUp } from "lucide-react"

import { PageLayout, StaggerContainer, StaggerItem } from "@/components/page-layout"
import { SectionHeader } from "@/components/section-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Wind,
  Server,
  ArrowRight,
  ArrowDown,
  RefreshCw,
  Layers,
  Database,
  Cpu,
  Building2,
  Globe,
  CheckCircle2,
} from "lucide-react"

// Component for visualizing clients/wind farms
function ClientNode({ name, id }: { name: string; id: string }) {
  return (
    <div className="flex flex-col items-center">
      <div className="relative">
        <div className="flex h-16 w-16 items-center justify-center rounded-xl border-2 border-primary/30 bg-card shadow-sm">
          <Building2 className="h-7 w-7 text-primary" />
        </div>
        <div className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-accent-foreground">
          {id}
        </div>
      </div>
      <span className="mt-2 text-xs font-medium text-muted-foreground">{name}</span>
    </div>
  )
}

// Animated arrow component
function FlowArrow({ direction = "down", label }: { direction?: "down" | "right" | "up"; label?: string }) {
  const Icon = direction === "right" ? ArrowRight : ArrowDown
  const rotateClass = direction === "up" ? "rotate-180" : ""
  
  return (
    <div className={`flex flex-col items-center ${direction === "right" ? "flex-row" : ""}`}>
      <div className={`p-2 ${rotateClass}`}>
        <Icon className="h-5 w-5 text-primary animate-pulse" />
      </div>
      {label && (
        <span className="text-[10px] text-muted-foreground font-medium whitespace-nowrap">{label}</span>
      )}
    </div>
  )
}

export default function ArchitecturePage() {
  return (
    <PageLayout>
      {/* Header */}
      <section className="bg-gradient-to-b from-primary/5 to-background">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <SectionHeader
              badge="Technical Overview"
              title="System Architecture"
              description=""
              centered
            />
          </div>
        </div>
      </section>

      {/* Main Architecture Diagram */}
      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <Card className="overflow-hidden pt-0">
          <CardHeader className="border-b bg-muted/50 pt-8">
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-primary" />
              Federated Learning Architecture
            </CardTitle>
            <CardDescription>
              Multiple wind farms collaborate to train a shared model without sharing raw data
            </CardDescription>
          </CardHeader>
          <CardContent className="p-8">
            <div className="flex flex-col items-center">
              {/* Clients Row */}
              <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-10">
                <ClientNode name="Wind Farm A" id="1" />
                <ClientNode name="Wind Farm B" id="2" />
                <ClientNode name="Wind Farm C" id="3" />
                <ClientNode name="Region D" id="4" />
              </div>

              {/* Bidirectional arrows */}
              <div className="my-6 flex items-center gap-4">
                <div className="flex flex-col items-center">
                  <ArrowDown className="h-5 w-5 text-primary" />
                  <span className="text-[10px] text-muted-foreground mt-1">Model Updates</span>
                </div>
                <div className="w-8" />
                <div className="flex flex-col items-center">
                  <ArrowDown className="h-5 w-5 text-accent rotate-180" />
                  <span className="text-[10px] text-muted-foreground mt-1">Global Model</span>
                </div>
              </div>

              {/* Central Server */}
              <div className="relative">
                <div className="flex h-24 w-40 flex-col items-center justify-center rounded-2xl border-2 border-accent bg-gradient-to-br from-accent/10 to-accent/5 shadow-lg">
                  <Server className="h-8 w-8 text-accent" />
                  <span className="mt-1 text-sm font-semibold text-foreground">Central Server</span>
                </div>
                <div className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-full bg-primary px-2 py-0.5 text-[10px] font-medium text-primary-foreground">
                  FedAvg
                </div>
              </div>

              {/* Output */}
              <FlowArrow direction="down" />

              <div className="flex h-16 w-48 items-center justify-center rounded-xl border border-border bg-card shadow-sm">
                <div className="text-center">
                  <Wind className="mx-auto h-5 w-5 text-primary" />
                  <span className="text-xs font-medium text-foreground">Aggregated Global Model</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>


      {/* Federated Learning Algorithms */}
      <section className="py-12 sm:py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeader
            badge="Algorithms"
            title="Federated Learning Algorithms"
            description=""
            centered
          />
        </div>
      </section>

      {/* FedAvg Detailed Explanation */}
      <section className="bg-muted/30 mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-2 items-start">
          <div>
            <SectionHeader
              badge="Core Algorithm"
              title="FedAvg: Federated Averaging (Default)"
              description="The foundational algorithm that powers privacy-preserving collaborative learning."
            />

            <div className="mt-6 space-y-4">
              <div>
                <h4 className="font-semibold text-foreground mb-2">Definition</h4>
                <p className="text-sm text-muted-foreground">
                  FedAvg computes a weighted average of model parameters from all participating clients based on their dataset sizes. 
                  This simple yet powerful approach enables global model training without centralizing data.
                </p>
              </div>

              <div>
                <h4 className="font-semibold text-foreground mb-2">How It Works</h4>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">1.</span> Server sends current global model to all clients
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">2.</span> Each client trains on local data for multiple epochs
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">3.</span> Clients send weight updates back to server
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">4.</span> Server aggregates updates as: w_global = Σ(n_k / n) × w_k
                  </li>
                </ul>
              </div>

              <div>
                <h4 className="font-semibold text-foreground mb-2">Why Use FedAvg</h4>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Communication efficient with multiple local epochs
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Convergence guarantees even with heterogeneous data
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Simple implementation and easy to understand
                  </li>
                </ul>
              </div>

              {/* <div>
                <h4 className="font-semibold text-foreground mb-2">Wind Forecasting Application</h4>
                <p className="text-sm text-muted-foreground">
                  Ideal when wind farms have similar data distributions. Works well for regions with comparable weather patterns.
                </p>
              </div> */}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">FedAvg Algorithm</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="rounded-lg bg-muted p-4">
                <code className="text-xs text-muted-foreground">
                  <span className="text-primary">// Federated Averaging</span>
                  <br />
                  <br />
                  <span className="text-foreground">for</span> each round r = 1, 2, ... :
                  <br />
                  &nbsp;&nbsp;<span className="text-foreground">for</span> each client k in parallel:
                  <br />
                  &nbsp;&nbsp;&nbsp;&nbsp;w_k ← LocalTrain(global_model, local_data_k)
                  <br />
                  <br />
                  &nbsp;&nbsp;<span className="text-accent">// Weighted average aggregation</span>
                  <br />
                  &nbsp;&nbsp;w_global ← Σ (n_k / n) × w_k
                  <br />
                  <br />
                  <span className="text-muted-foreground">// n_k = local dataset size</span>
                  <br />
                  <span className="text-muted-foreground">// n = total samples</span>
                </code>
              </div>
              <div>
                <h4 className="font-semibold text-xs text-foreground mb-2">Advantages</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Mathematically proven convergence</li>
                  <li>• Handles non-IID data reasonably well</li>
                  <li>• Minimal overhead for aggregation</li>
                </ul>
              </div>
              <div>
                <h4 className="font-semibold text-xs text-foreground mb-2">Trade-offs</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Can struggle with highly heterogeneous data</li>
                  <li>• No built-in personalization capability</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* FedProx Detailed Explanation */}
      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-2 items-start">
          <div>
            <SectionHeader
              badge="Algorithm"
              title="FedProx: Proximal Term Regularization"
              description="Addresses data heterogeneity and system heterogeneity in federated learning."
            />

            <div className="mt-6 space-y-4">
              <div>
                <h4 className="font-semibold text-foreground mb-2">Definition</h4>
                <p className="text-sm text-muted-foreground">
                  FedProx adds a proximal term (regularization penalty) to each client's local training objective. 
                  This term penalizes updates that drift too far from the global model, preventing divergence in heterogeneous settings.
                </p>
              </div>

              <div>
                <h4 className="font-semibold text-foreground mb-2">How It Works</h4>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">1.</span> Modify local loss: L(w) + (μ/2)||w - w_global||²
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">2.</span> Each client minimizes their modified loss locally
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">3.</span> Server aggregates using weighted averaging (like FedAvg)
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">4.</span> The μ parameter (proximal coefficient) controls drift tolerance
                  </li>
                </ul>
              </div>

              <div>
                <h4 className="font-semibold text-foreground mb-2">Why Use FedProx</h4>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Handles non-IID data better than FedAvg
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Robust to device heterogeneity (slow/fast clients)
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Improves training stability in heterogeneous networks
                  </li>
                </ul>
              </div>

              {/* <div>
                <h4 className="font-semibold text-foreground mb-2">Wind Forecasting Application</h4>
                <p className="text-sm text-muted-foreground">
                  Recommended for multi-regional wind farms with different weather patterns. Handles disparate data distributions across regions.
                </p>
              </div> */}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">FedProx Modification</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="rounded-lg bg-muted p-4">
                <code className="text-xs text-muted-foreground">
                  <span className="text-primary">// Local objective with proximal term</span>
                  <br />
                  <br />
                  <span className="text-foreground">minimize</span> L(w) + (μ/2)||w - w_t||²
                  <br />
                  <br />
                  <span className="text-primary">// Where:</span>
                  <br />
                  <span className="text-muted-foreground">// L(w) = original loss on local data</span>
                  <br />
                  <span className="text-muted-foreground">// w_t = global model at round t</span>
                  <br />
                  <span className="text-muted-foreground">// μ = proximal coefficient (typical: 0.01-0.1)</span>
                  <br />
                  <br />
                  <span className="text-accent">// Aggregation remains the same as FedAvg</span>
                </code>
              </div>
              <div>
                <h4 className="font-semibold text-xs text-foreground mb-2">Advantages</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Better convergence with heterogeneous data</li>
                  <li>• Tolerates system heterogeneity</li>
                  <li>• Backward compatible with FedAvg (μ=0)</li>
                </ul>
              </div>
              <div>
                <h4 className="font-semibold text-xs text-foreground mb-2">Trade-offs</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Requires tuning μ parameter</li>
                  <li>• Slightly increased computation cost per client</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* FedOPT Detailed Explanation */}
      <section className="bg-muted/30 mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="grid gap-8 items-start lg:grid-cols-2">
          <div>
            <SectionHeader
              badge="Algorithm"
              title="FedOPT: Federated Optimization"
              description="Improves federated training by applying adaptive server-side optimization instead of plain parameter averaging."
            />

            <div className="mt-6 space-y-4">
              <div>
                <h4 className="mb-2 font-semibold text-foreground">Definition</h4>
                <p className="text-sm text-muted-foreground">
                  FedOPT is a federated learning approach where clients still train locally, but the server updates the
                  global model using an optimizer such as Adam, Adagrad, or Yogi. Instead of relying only on standard
                  weighted averaging, the server performs a more informed optimization step on the aggregated updates.
                </p>
              </div>

              <div>
                <h4 className="mb-2 font-semibold text-foreground">How It Works</h4>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">1.</span> Each client trains the current global model on its local dataset
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">2.</span> Clients send model updates or weights back to the server
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">3.</span> The server aggregates these client updates into a global update signal
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">4.</span> The server applies an optimizer step to update the global model parameters
                  </li>
                </ul>
              </div>

              <div>
                <h4 className="mb-2 font-semibold text-foreground">Why Use FedOPT</h4>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Better convergence than plain FedAvg in many settings
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> More stable training on heterogeneous client data
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Supports adaptive optimizers for improved global updates
                  </li>
                </ul>
              </div>

              {/* <div>
                <h4 className="mb-2 font-semibold text-foreground">Wind Forecasting Application</h4>
                <p className="text-sm text-muted-foreground">
                  FedOPT is useful in wind forecasting because wind farms often have non-IID data distributions.
                  Adaptive server-side optimization can improve stability and global model quality across geographically
                  different clients.
                </p>
              </div> */}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">FedOPT Update Structure</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="rounded-lg bg-muted p-4">
                <code className="text-xs text-muted-foreground">
                  <span className="text-primary">// Client-server optimization flow</span>
                  <br />
                  <br />
                  <span className="text-accent">CLIENT SIDE</span>:
                  <br />
                  &nbsp;&nbsp;w_k ← local_train(w_t)
                  <br />
                  &nbsp;&nbsp;Δ_k ← w_k - w_t
                  <br />
                  <br />
                  <span className="text-accent">SERVER SIDE</span>:
                  <br />
                  &nbsp;&nbsp;Δ ← aggregate(Δ_1, ..., Δ_K)
                  <br />
                  &nbsp;&nbsp;w_(t+1) ← OptimizerUpdate(w_t, Δ)
                  <br />
                  <br />
                  <span className="text-primary">// Example optimizers</span>
                  <br />
                  &nbsp;&nbsp;FedAdam, FedAdagrad, FedYogi
                </code>
              </div>
              <div>
                <h4 className="mb-2 text-xs font-semibold text-foreground">Advantages</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Stronger optimization at the server</li>
                  <li>• Handles non-IID data more effectively</li>
                  <li>• Flexible choice of adaptive optimizers</li>
                </ul>
              </div>
              <div>
                <h4 className="mb-2 text-xs font-semibold text-foreground">Trade-offs</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• More tuning needed for server hyperparameters</li>
                  <li>• Slightly more complex than plain FedAvg</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* FedPer Detailed Explanation */}
      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-2 items-start">
          <div>
            <SectionHeader
              badge="Algorithm"
              title="FedPer: Federated Personalization"
              description="Explicit model separation into global and personalized components for maximum customization."
            />

            <div className="mt-6 space-y-4">
              <div>
                <h4 className="font-semibold text-foreground mb-2">Definition</h4>
                <p className="text-sm text-muted-foreground">
                  FedPer partitions each model into two distinct parts: a shared base model (aggregated globally) 
                  and personalized head model (kept locally). This enables both collaborative learning and individual customization.
                </p>
              </div>

              <div>
                <h4 className="font-semibold text-foreground mb-2">How It Works</h4>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">1.</span> Define split point: base layers (shared) + head layers (personal)
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">2.</span> Server sends base model to all clients
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">3.</span> Each client trains full model (base + head) on local data
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">4.</span> Only base model weights sent back and aggregated
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent shrink-0">5.</span> Each client retains trained head model for predictions
                  </li>
                </ul>
              </div>

              <div>
                <h4 className="font-semibold text-foreground mb-2">Why Use FedPer</h4>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Strongest personalization capability
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Leverages global knowledge + local expertise
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Proven higher accuracy on heterogeneous tasks
                  </li>
                </ul>
              </div>

              {/* <div>
                <h4 className="font-semibold text-foreground mb-2">Wind Forecasting Application</h4>
                <p className="text-sm text-muted-foreground">
                  Excellent for diverse wind farms with unique local characteristics. Base model learns universal wind patterns; 
                  head learns farm-specific dynamics (terrain, obstacles, seasonal variations).
                </p>
              </div> */}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">FedPer Architecture</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="rounded-lg bg-muted p-4">
                <code className="text-xs text-muted-foreground">
                  <span className="text-primary">// Model architecture split</span>
                  <br />
                  <br />
                  model = [base_model, head_model]
                  <br />
                  <br />
                  <span className="text-accent">// Aggregation strategy</span>
                  <br />
                  <span className="text-foreground">for</span> each round:
                  <br />
                  &nbsp;&nbsp;base_k ← train(base, head_k, local_data)
                  <br />
                  &nbsp;&nbsp;base_global ← aggregate(base_k)
                  <br />
                  &nbsp;&nbsp;head_k ← keep locally (not aggregated)
                  <br />
                  <br />
                  <span className="text-muted-foreground">// Prediction uses full model</span>
                  <br />
                  &nbsp;&nbsp;pred ← base_global + head_k
                </code>
              </div>
              <div>
                <h4 className="font-semibold text-xs text-foreground mb-2">Advantages</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Maximum personalization</li>
                  <li>• Learns universal + specific patterns</li>
                  <li>• Higher accuracy on diverse data</li>
                </ul>
              </div>
              <div>
                <h4 className="font-semibold text-xs text-foreground mb-2">Trade-offs</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Requires careful architecture design</li>
                  <li>• More client-side storage for heads</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* FedLN Detailed Explanation */}
      <section className="bg-muted/30 mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="grid gap-8 items-start lg:grid-cols-2">
          <div>
            <SectionHeader
              badge="Algorithm"
              title="FedLN: Federated Layer Normalization"
              description="Improves federated training stability by using layer normalization, which is less sensitive to client heterogeneity and batch size differences."
            />

            <div className="mt-6 space-y-4">
              <div>
                <h4 className="mb-2 font-semibold text-foreground">Definition</h4>
                <p className="text-sm text-muted-foreground">
                  FedLN is a federated learning approach that uses Layer Normalization instead of Batch Normalization to
                  make training more stable across clients. Since Layer Normalization operates within each sample rather
                  than across the batch, it is better suited for federated settings with non-IID data and varying local
                  batch sizes.
                </p>
              </div>

              <div>
                <h4 className="mb-2 font-semibold text-foreground">How It Works</h4>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">1.</span> Replace Batch Normalization layers with Layer Normalization layers
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">2.</span> Each client trains the shared model locally using its own data
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">3.</span> Layer normalization computes statistics per sample, not across the batch
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">4.</span> Client updates are aggregated normally at the server into the global model
                  </li>
                </ul>
              </div>

              <div>
                <h4 className="mb-2 font-semibold text-foreground">Why Use FedLN</h4>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> More stable than BatchNorm with small local batch sizes
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Better suited for heterogeneous client data distributions
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Simpler normalization behavior across federated clients
                  </li>
                </ul>
              </div>

              {/* <div>
                <h4 className="mb-2 font-semibold text-foreground">Wind Forecasting Application</h4>
                <p className="text-sm text-muted-foreground">
                  FedLN can help in wind forecasting when different wind farms have uneven data volumes and varying local
                  data distributions. Layer normalization improves training consistency without depending on batch-level
                  statistics.
                </p>
              </div> */}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">FedLN Algorithm</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="rounded-lg bg-muted p-4">
                <code className="text-xs text-muted-foreground">
                  <span className="text-primary">// Layer normalization mechanism</span>
                  <br />
                  <br />
                  <span className="text-accent">// At each client:</span>
                  <br />
                  &nbsp;&nbsp;replace BatchNorm with LayerNorm
                  <br />
                  &nbsp;&nbsp;train local model on client data
                  <br />
                  &nbsp;&nbsp;normalize activations per sample
                  <br />
                  <br />
                  <span className="text-accent">// At server:</span>
                  <br />
                  &nbsp;&nbsp;collect client model updates
                  <br />
                  &nbsp;&nbsp;aggregate updates into global model
                  <br />
                  <br />
                  <span className="text-muted-foreground">// Reduces sensitivity to batch statistics</span>
                </code>
              </div>
              <div>
                <h4 className="mb-2 text-xs font-semibold text-foreground">Advantages</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Stable with small batch sizes</li>
                  <li>• Works well under non-IID data</li>
                  <li>• No dependence on batch-level statistics</li>
                </ul>
              </div>
              <div>
                <h4 className="mb-2 text-xs font-semibold text-foreground">Trade-offs</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• May differ from standard CNN BatchNorm setups</li>
                  <li>• Can be less common in some vision architectures</li>
                  <li>• Requires model design compatibility with LayerNorm</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

            {/* StatAvg Detailed Explanation */}
      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="grid gap-8 items-start lg:grid-cols-2">
          <div>
            <SectionHeader
              badge="Algorithm"
              title="StatAvg: Statistical Averaging"
              description="Mitigates feature distribution heterogeneity by sharing and averaging client-side data statistics before federated training."
            />

            <div className="mt-6 space-y-4">
              <div>
                <h4 className="mb-2 font-semibold text-foreground">Definition</h4>
                <p className="text-sm text-muted-foreground">
                  StatAvg is a federated learning method designed to reduce non-IID feature distribution differences
                  across clients. Each client computes local statistics such as feature means and variances, the server
                  aggregates them into global statistics, and these are used for consistent data normalization before or
                  alongside the main federated training process.
                </p>
              </div>

              <div>
                <h4 className="mb-2 font-semibold text-foreground">How It Works</h4>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">1.</span> Each client computes local feature statistics from its own dataset
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">2.</span> Clients send these statistics, not raw data, to the server
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">3.</span> The server averages the received statistics to produce global normalization values
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 text-accent">4.</span> Clients use the shared global statistics for more consistent local training
                  </li>
                </ul>
              </div>

              <div>
                <h4 className="mb-2 font-semibold text-foreground">Why Use StatAvg</h4>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Reduces feature-level heterogeneity across clients
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Improves normalization consistency in non-IID settings
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent">•</span> Can be combined with standard FL aggregation methods
                  </li>
                </ul>
              </div>

              {/* <div>
                <h4 className="mb-2 font-semibold text-foreground">Wind Forecasting Application</h4>
                <p className="text-sm text-muted-foreground">
                  StatAvg can help when wind farms have noticeably different feature distributions. Shared global
                  normalization statistics can make training inputs more consistent before federated model aggregation.
                </p>
              </div> */}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">StatAvg Algorithm</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="rounded-lg bg-muted p-4">
                <code className="text-xs text-muted-foreground">
                  <span className="text-primary">// Statistical averaging mechanism</span>
                  <br />
                  <br />
                  <span className="text-accent">// At each client:</span>
                  <br />
                  &nbsp;&nbsp;compute local mean and variance
                  <br />
                  &nbsp;&nbsp;send statistics to server
                  <br />
                  <br />
                  <span className="text-accent">// At server:</span>
                  <br />
                  &nbsp;&nbsp;μ_global ← average(μ_1, ..., μ_K)
                  <br />
                  &nbsp;&nbsp;σ²_global ← average(σ²_1, ..., σ²_K)
                  <br />
                  <br />
                  <span className="text-accent">// Back to clients:</span>
                  <br />
                  &nbsp;&nbsp;normalize local data using μ_global and σ²_global
                  <br />
                  &nbsp;&nbsp;run federated training as usual
                  <br />
                  <br />
                  <span className="text-muted-foreground">// Reduces non-IID feature distribution mismatch</span>
                </code>
              </div>
              <div>
                <h4 className="mb-2 text-xs font-semibold text-foreground">Advantages</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Better global normalization consistency</li>
                  <li>• Helps with heterogeneous feature distributions</li>
                  <li>• Works with existing FL aggregation methods</li>
                </ul>
              </div>
              <div>
                <h4 className="mb-2 text-xs font-semibold text-foreground">Trade-offs</h4>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li>• Adds a statistics-sharing step before training</li>
                  <li>• Mainly helps feature heterogeneity, not all FL issues</li>
                  <li>• Effectiveness depends on useful shared statistics</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>


      {/* LLM Models */}
      <section className="bg-muted/50 py-12 sm:py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SectionHeader
            badge="Models"
            title="Supported LLM Models for Wind Forecasting"
            description=""
            centered
          />

          <div className="mt-12 grid gap-6 md:grid-cols-2">
            {/* GPT4TS */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  GPT4TS
                </CardTitle>
                <CardDescription>GPT-based Time Series Model</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p className="text-muted-foreground">
                  Generative Pre-trained Transformer adapted for time-series forecasting with strong performance on univariate and multivariate sequences.
                </p>
                <div className="space-y-2">
                  <h4 className="font-medium text-xs text-foreground">Key Features:</h4>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Attention mechanisms for temporal patterns
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Pre-trained knowledge transfer
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Handles irregular sampling
                    </li>
                  </ul>
                </div>
              </CardContent>
            </Card>

            {/* LLAMA */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  LLAMA
                </CardTitle>
                <CardDescription>Large Language Model Meta AI</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p className="text-muted-foreground">
                  Meta's open-source language model optimized for efficiency and adapted for time-series wind speed prediction.
                </p>
                <div className="space-y-2">
                  <h4 className="font-medium text-xs text-foreground">Key Features:</h4>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Efficient inference
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Reduced model size
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Better edge deployment
                    </li>
                  </ul>
                </div>
              </CardContent>
            </Card>

            {/* BERT */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  BERT
                </CardTitle>
                <CardDescription>Bidirectional Encoder Representations</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p className="text-muted-foreground">
                  Bidirectional transformer model that captures context from both directions for improved wind forecasting accuracy.
                </p>
                <div className="space-y-2">
                  <h4 className="font-medium text-xs text-foreground">Key Features:</h4>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Bidirectional context
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Strong representation learning
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Good for feature extraction
                    </li>
                  </ul>
                </div>
              </CardContent>
            </Card>

            {/* BART */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  BART
                </CardTitle>
                <CardDescription>Denoising Sequence-to-Sequence Model</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p className="text-muted-foreground">
                  Combines BERT encoder and GPT decoder for sequence-to-sequence tasks, excellent for wind speed sequence prediction.
                </p>
                <div className="space-y-2">
                  <h4 className="font-medium text-xs text-foreground">Key Features:</h4>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Sequence-to-sequence capability
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Denoising pre-training
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Multi-horizon forecasting
                    </li>
                  </ul>
                </div>
              </CardContent>
            </Card>

            {/* Qwen */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  Qwen
                </CardTitle>
                <CardDescription>Efficient Open-Source Transformer Model</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p className="text-muted-foreground">
                  Strong open-source transformer model suitable for adapting sequence modeling and forecasting workflows in wind prediction tasks.
                </p>
                <div className="space-y-2">
                  <h4 className="font-medium text-xs text-foreground">Key Features:</h4>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Strong general language understanding
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Efficient fine-tuning potential
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Adaptable to sequence forecasting tasks
                    </li>
                  </ul>
                </div>
              </CardContent>
            </Card>

            {/* Gemma */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  Gemma
                </CardTitle>
                <CardDescription>Lightweight Open Language Model</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p className="text-muted-foreground">
                  Compact open model designed for efficient deployment, making it useful for resource-aware wind forecasting and edge-oriented experiments.
                </p>
                <div className="space-y-2">
                  <h4 className="font-medium text-xs text-foreground">Key Features:</h4>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Lightweight architecture
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Efficient deployment on limited hardware
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Good for scalable experimentation
                    </li>
                  </ul>
                </div>
              </CardContent>
            </Card>

            {/* OPT */}
            <Card className="md:col-span-2 md:mx-auto md:w-[calc(50%-0.75rem)]">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  OPT
                </CardTitle>
                <CardDescription>Open Pre-trained Transformer</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p className="text-muted-foreground">
                  Meta&apos;s open pre-trained transformer family provides a flexible baseline for adapting large language models to wind forecasting and temporal prediction tasks.
                </p>
                <div className="space-y-2">
                  <h4 className="font-medium text-xs text-foreground">Key Features:</h4>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Open and reproducible model family
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Suitable as a strong research baseline
                    </li>
                    <li className="flex gap-2">
                      <span className="text-accent">•</span> Flexible adaptation for forecasting tasks
                    </li>
                  </ul>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

    </PageLayout>
  )
}

// Import icons that were used in the component
function Download(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" x2="12" y1="15" y2="3" />
    </svg>
  )
}

function Upload(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" x2="12" y1="3" y2="15" />
    </svg>
  )
}
