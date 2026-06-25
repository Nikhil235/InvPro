import * as React from "react"
import { cn } from "../../lib/utils"

const Badge = React.forwardRef(({ className, variant = "default", ...props }, ref) => {
  const variants = {
    default: "bg-surface text-primary border-border",
    bullish: "bg-bullish-muted text-bullish border-bullish/20",
    bearish: "bg-bearish-muted text-bearish border-bearish/20",
    neutral: "bg-surface text-neutral border-neutral/20",
    gold: "bg-gold/20 text-gold border-gold/20",
  }

  return (
    <div
      ref={ref}
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        variants[variant] || variants.default,
        className
      )}
      {...props}
    />
  )
})
Badge.displayName = "Badge"

export { Badge }
