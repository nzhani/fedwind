interface SectionHeaderProps {
  badge?: string
  title: string
  description?: string
  centered?: boolean
}

// Reusable section header component with optional badge
export function SectionHeader({ badge, title, description, centered = false }: SectionHeaderProps) {
  return (
    <div className={`space-y-3 ${centered ? "text-center" : ""}`}>
      {badge && (
        <span className="inline-block rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
          {badge}
        </span>
      )}
      <h2 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl text-balance">
        {title}
      </h2>
      {description && (
        <p className="max-w-2xl text-muted-foreground leading-relaxed text-pretty">
          {description}
        </p>
      )}
    </div>
  )
}
