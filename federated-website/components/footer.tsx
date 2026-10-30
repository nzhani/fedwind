import { Wind } from "lucide-react"
import Link from "next/link"

export function Footer() {
  return (
    <footer className="border-t border-border bg-card">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid gap-8 md:grid-cols-3">
          {/* Brand Section */}
          <div className="space-y-4">
            <Link href="/" className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
                <Wind className="h-4 w-4 text-primary-foreground" />
              </div>
              <span className="text-lg font-semibold text-foreground">FedWind</span>
            </Link>
            {/* <p className="text-sm text-muted-foreground leading-relaxed">
              Privacy-preserving wind speed and power forecasting using Federated Learning and Large Language Models.
            </p> */}
          </div>

          {/* Quick Links */}
          <div>
            <h3 className="mb-4 text-sm font-semibold text-foreground">Quick Links</h3>
            <ul className="space-y-2">
              {[
                { href: "/instructions", label: "Instructions" },
                { href: "/architecture", label: "System Architecture" },
                { href: "/data-source", label: "Data Source" },
                { href: "/dashboard", label: "Dashboard Demo" },
                { href: "/about", label: "About Project" },
              ].map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-primary"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Research Info */}
          <div>
            <h3 className="mb-4 text-sm font-semibold text-foreground">Research Project</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              This is a university research project focused on developing privacy-preserving machine learning solutions for renewable energy forecasting.
            </p>
            <p className="mt-3 text-sm text-muted-foreground">
              Built with Federated Learning, Transformer-based LLMs, and PyTorch.
            </p>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="mt-8 border-t border-border pt-8">
          <p className="text-center text-sm text-muted-foreground">
            {new Date().getFullYear()} FedWind Research Project. For academic and research purposes.
          </p>
        </div>
      </div>
    </footer>
  )
}
